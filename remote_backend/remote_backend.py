#!/usr/bin/env python3
"""
Remote File Browser Backend for vib_viewer
===========================================
Serves file listings and file content from a remote filesystem
to the vib_viewer running in your browser.

Quick start
-----------
1. Copy this file to your remote machine.
2. Install dependencies (one-time):

       pip install fastapi uvicorn

3. Start the server:

       python remote_backend.py

   The server prints the port to use (derived from your UID by default):

       Port: 1042  →  ssh -L 8765:localhost:1042 user@remote-host

   Default browsing root is $HOME. Override with VIB_ROOT:

       VIB_ROOT=/data/projects python remote_backend.py

   Add named shortcut chips to the UI with VIB_ROOTS:

       VIB_ROOTS="scratch=/scratch/myuser,work=/data/work" python remote_backend.py

   Force a specific port with VIB_PORT:

       VIB_PORT=9000 python remote_backend.py

4. On your local machine, open an SSH tunnel using the printed port:

       ssh -L 8765:localhost:<PORT> user@remote-host

5. Open vib_viewer in your browser and click "📂 Remote Files".

Environment variables
---------------------
VIB_ROOT    Single root directory the server is allowed to serve.
            Defaults to $HOME.

VIB_ROOTS   Comma-separated name=path pairs for the shortcut chips
            shown at the top of the file picker dialog.
            Example: VIB_ROOTS="scratch=/scratch/myuser,proj=/data/proj"
            Each path must exist and be a directory.
            "home" is always added automatically pointing to VIB_ROOT.

VIB_PORT    Port to listen on. Defaults to your UID (unique per user
            account, avoids conflicts on shared machines). Set this if
            you need a specific port.

Security
--------
The server only responds to GET requests and only serves files/directories
that fall under one of the configured roots. It binds to 127.0.0.1 only,
so it is not reachable from outside the machine without an SSH tunnel.
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import os
import socket

app = FastAPI(title="vib_viewer remote file browser")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://appendko.github.io",
        "http://localhost",
        "http://127.0.0.1",
    ],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ── allowed roots ────────────────────────────────────────────────────────────

ALLOWED_ROOT = Path(os.environ.get("VIB_ROOT", Path.home())).resolve()


def _parse_roots():
    roots = {}
    for item in os.environ.get("VIB_ROOTS", "").split(","):
        item = item.strip()
        if "=" in item:
            name, path = item.split("=", 1)
            p = Path(path.strip()).resolve()
            if p.exists() and p.is_dir():
                roots[name.strip()] = str(p)
    roots.setdefault("home", str(ALLOWED_ROOT))
    return roots


ROOTS = _parse_roots()
_ALLOWED_ROOTS = list({Path(p) for p in ROOTS.values()} | {ALLOWED_ROOT})

VIB_EXTENSIONS = {".log", ".out", ".hess", ".fchk", ".json", ".cjson"}

MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB


def safe_path(path: str) -> Path:
    """Resolve path and verify it falls under at least one allowed root."""
    p = Path(path).resolve()
    for root in _ALLOWED_ROOTS:
        try:
            p.relative_to(root)
            return p
        except ValueError:
            pass
    raise HTTPException(status_code=403, detail="Path outside allowed roots")


# ── endpoints ─────────────────────────────────────────────────────────────────

@app.get("/api/ping")
def ping():
    """Health check — also returns named roots for the UI chip bar."""
    return {"status": "ok", "allowed_root": str(ALLOWED_ROOT), "roots": ROOTS}


@app.get("/api/ls")
def list_dir(path: str = Query(default=str(ALLOWED_ROOT)),
             exts: str = Query(default="")):
    """
    List directory contents (folders first, then files, both sorted
    alphabetically). parent is null when at a root directory.
    exts: optional comma-separated extension filter e.g. ".log,.out".
    If omitted or empty, all non-hidden files are listed.
    """
    p = safe_path(path)

    if not p.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {path}")
    if not p.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {path}")

    ext_filter = {e.strip().lower() for e in exts.split(",") if e.strip()} if exts else None

    entries = []
    try:
        for item in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if item.name.startswith("."):
                continue
            is_dir = item.is_dir()
            if is_dir or ext_filter is None or item.suffix.lower() in ext_filter:
                entries.append({
                    "name": item.name,
                    "path": str(item),
                    "is_dir": is_dir,
                    "size": item.stat().st_size if not is_dir else None,
                })
    except PermissionError:
        raise HTTPException(status_code=403, detail=f"Permission denied: {path}")

    at_root = p in _ALLOWED_ROOTS
    return {
        "path": str(p),
        "parent": None if at_root else str(p.parent),
        "entries": entries,
    }


@app.get("/api/file")
def read_file(path: str = Query(...)):
    """Return the text content of a supported file."""
    p = safe_path(path)

    if not p.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    if not p.is_file():
        raise HTTPException(status_code=400, detail=f"Not a file: {path}")
    if p.stat().st_size > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large (max {MAX_FILE_BYTES // 1024 // 1024} MB)")

    try:
        content = p.read_text(errors="replace")
    except PermissionError:
        raise HTTPException(status_code=403, detail=f"Permission denied: {path}")

    return {"filename": p.name, "path": str(p), "content": content}


def get_port():
    """Return the port to listen on.

    If VIB_PORT is set, use it as-is (uvicorn will fail if it's taken).
    Otherwise try the user's UID (memorable, unique per account); fall back
    to an OS-assigned free port if the UID port is already in use.
    """
    user_specified = os.environ.get("VIB_PORT")
    if user_specified:
        return int(user_specified)
    preferred = os.getuid()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]


if __name__ == "__main__":
    import uvicorn
    port = get_port()
    print(f"Serving files under: {ALLOWED_ROOT}")
    print(f"Named roots: {ROOTS}")
    print(f"Port: {port}  →  ssh -L 8765:localhost:{port} user@remote-host")
    uvicorn.run(app, host="127.0.0.1", port=port)
