# vib_viewer HPC backend

A small FastAPI server that lets the vib_viewer browser app browse and load files from a remote machine (HPC cluster, lab server, etc.) through an SSH tunnel.

## Requirements

Python 3.8+ with FastAPI and Uvicorn:

```sh
pip install fastapi uvicorn
```

## Usage

### 1. Start the server on the remote machine

```sh
# Default: browse from $HOME
python hpc_server.py

# Custom root
VIB_ROOT=/data/projects python hpc_server.py

# Named shortcut chips in the UI
VIB_ROOTS="scratch=/scratch/myuser,work=/data/work" python hpc_server.py
```

### 2. Open an SSH tunnel on your local machine

```sh
ssh -L 8765:localhost:8765 user@remote-host
```

### 3. Open vib_viewer and click "📂 HPC Files"

The status dot turns green when the tunnel is active. Click a folder to navigate, click a file to load it directly into the viewer.

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `VIB_ROOT` | `$HOME` | Root directory the server is allowed to serve. Browsing is restricted to this tree. |
| `VIB_ROOTS` | — | Comma-separated `name=path` pairs for shortcut chips in the UI. Example: `scratch=/scratch/myuser,proj=/data/proj`. Each path must exist. `home` pointing to `VIB_ROOT` is always added automatically. |

## Supported file types

`.log`, `.out`, `.hess`, `.fchk`, `.json`, `.cjson`

## Security notes

- The server binds to `127.0.0.1` only — not reachable without an SSH tunnel.
- All requests are GET-only (read-only filesystem access).
- Every path is validated against the configured roots before being served; requests outside those trees return 403.
