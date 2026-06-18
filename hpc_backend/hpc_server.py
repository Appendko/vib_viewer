#!/usr/bin/env python3
"""
HPC File Browser Backend for vib_viewer
========================================
Serves file listings and file content from a remote filesystem
to the vib_viewer running in your browser.

Quick start
-----------
1. Copy this file to your remote machine.
2. Install dependencies (one-time):

       pip install fastapi uvicorn

3. Start the server:

       python hpc_server.py

   Default browsing root is $HOME. Override with VIB_ROOT:

       VIB_ROOT=/data/projects python hpc_server.py

   Add named shortcut chips to the UI with VIB_ROOTS:

       VIB_ROOTS="scratch=/scratch/myuser,work=/data/work" python hpc_server.py

4. On your local machine, open an SSH tunnel:

       ssh -L 8765:localhost:8765 user@remote-host

5. Open vib_viewer in your browser and click "📂 HPC Files".

Environment variables
---------------------
VIB_ROOT    Single root directory the server is allowed to serve.
            Defaults to $HOME.

VIB_ROOTS   Comma-separated name=path pairs for the shortcut chips
            shown at the top of the file picker dialog.
            Example: VIB_ROOTS="scratch=/scratch/myuser,proj=/data/proj"
            Each path must exist and be a directory.
            "home" is always added automatically pointing to VIB_ROOT.

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

app = FastAPI(title="vib_viewer remote backend")

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

SUPPORTED_EXTENSIONS = {".log", ".out", ".hess", ".fchk", ".json", ".cjson"}


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
def list_dir(path: str = Query(default=str(ALLOWED_ROOT))):
    """
    List directory contents (folders first, then supported files, both
    sorted alphabetically). parent is null when at a root directory,
    which disables the ↑ button in the UI.
    """
    p = safe_path(path)

    if not p.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {path}")
    if not p.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {path}")

    entries = []
    try:
        for item in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if item.name.startswith("."):
                continue
            is_dir = item.is_dir()
            if is_dir or item.suffix.lower() in SUPPORTED_EXTENSIONS:
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
    if p.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {p.suffix}")

    try:
        content = p.read_text(errors="replace")
    except PermissionError:
        raise HTTPException(status_code=403, detail=f"Permission denied: {path}")

    return {"filename": p.name, "path": str(p), "content": content}


if __name__ == "__main__":
    import uvicorn
    print(f"Serving files under: {ALLOWED_ROOT}")
    print(f"Named roots: {ROOTS}")
    uvicorn.run(app, host="127.0.0.1", port=8765)
