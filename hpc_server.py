#!/usr/bin/env python3
"""
HPC File Browser Backend for vib_viewer
========================================
Serves file listings and file content from the HPC filesystem
to the vib_viewer running on https://appendko.github.io

Usage:
    pip install fastapi uvicorn
    python hpc_server.py

    # With named root shortcuts shown as chips in the UI:
    VIB_ROOTS="scratch=/scratch/user,work=/home/user/projects" python hpc_server.py

Then on your Mac:
    ssh -L 8765:localhost:8765 user@hpc

Open vib_viewer in your browser and click "📂 HPC Files".
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import os

app = FastAPI(title="vib_viewer HPC backend")

# Allow requests from GitHub Pages (and localhost for testing)
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

# ── safety: restrict browsing to paths under this root ──────────────────────
ALLOWED_ROOT = Path(os.environ.get("VIB_ROOT", Path.home())).resolve()

# ── named shortcuts shown as chips in the UI ────────────────────────────────
# Format: VIB_ROOTS="name=/path,name2=/path2"
def _parse_roots() -> dict:
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

# All directories the browser is allowed to browse under
_ALLOWED_ROOTS = list({Path(p) for p in ROOTS.values()} | {ALLOWED_ROOT})

SUPPORTED_EXTENSIONS = {".log", ".out", ".hess", ".fchk", ".json", ".cjson"}


def safe_path(path: str) -> Path:
    """Resolve path and ensure it falls under at least one allowed root."""
    p = Path(path).resolve()
    for root in _ALLOWED_ROOTS:
        try:
            p.relative_to(root)
            return p
        except ValueError:
            pass
    raise HTTPException(status_code=403, detail=f"Path outside allowed roots")


# ── endpoints ────────────────────────────────────────────────────────────────

@app.get("/api/ping")
def ping():
    """Health check — returns roots for the UI chip bar."""
    return {"status": "ok", "allowed_root": str(ALLOWED_ROOT), "roots": ROOTS}


@app.get("/api/ls")
def list_dir(path: str = Query(default=str(ALLOWED_ROOT))):
    """
    List directory contents.
    Returns folders first, then supported files, both sorted alphabetically.
    parent is null when already at a root directory (disables the ↑ button).
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
    print(f"Override root with: VIB_ROOT=/path/to/data python hpc_server.py")
    print(f"Add shortcuts with: VIB_ROOTS=\"scratch=/scratch/user,work=/home/user/work\" python hpc_server.py")
    uvicorn.run(app, host="127.0.0.1", port=8765)
