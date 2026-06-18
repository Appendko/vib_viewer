# vib_viewer remote backend

A small FastAPI server that lets the vib_viewer browser app browse and load files from any remote machine (lab server, cloud instance, etc.) through an SSH tunnel.

## Requirements

Python 3.8+ with FastAPI and Uvicorn:

```sh
pip install -r requirements.txt
```

## Usage

### 1. Start the server on the remote machine

```sh
# Default: browse from $HOME, port auto-selected from your UID
python remote_backend.py

# Custom root
VIB_ROOT=/data/projects python remote_backend.py

# Named shortcut chips in the UI
VIB_ROOTS="scratch=/scratch/myuser,work=/data/work" python remote_backend.py
```

The server prints the port to use for the SSH tunnel:

```
Port: 1042  →  ssh -L 8765:localhost:1042 user@remote-host
```

### 2. Open an SSH tunnel on your local machine

Use the port printed by the server:

```sh
ssh -L 8765:localhost:<PORT> user@remote-host
```

The left side (`8765`) is the local port your browser connects to — always fixed.
The right side is the server's port, unique to your account.

You can save this in `~/.ssh/config` so you never have to type it again:

```
Host remote-vib
    HostName remote-host
    User myuser
    LocalForward 8765 localhost:<PORT>
```

Then just `ssh remote-vib`.

### 3. Open vib_viewer and click "📂 Remote Files"

The status dot turns green when the tunnel is active. Click a folder to navigate, click a file to load it directly into the viewer.

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `VIB_ROOT` | `$HOME` | Root directory the server is allowed to serve. Browsing is restricted to this tree. |
| `VIB_ROOTS` | — | Comma-separated `name=path` pairs for shortcut chips in the UI. Example: `scratch=/scratch/myuser,proj=/data/proj`. Each path must exist. `home` pointing to `VIB_ROOT` is always added automatically. |
| `VIB_PORT` | UID-derived | Port to listen on. By default the server uses your user ID as the port number (unique per account, no conflicts on shared machines). Set this if you need a specific port. |

## Supported file types

vib_viewer: `.log`, `.out`, `.hess`, `.fchk`, `.json`, `.cjson`

spectra_viewer: `.peak`, `.spec`, `.jdx`, `.dx`, `.csv`, `.txt`, `.dat`

## Security notes

- The server binds to `127.0.0.1` only — not reachable without an SSH tunnel.
- All requests are GET-only (read-only filesystem access).
- Every path is validated against the configured roots before being served; requests outside those trees return 403.
- Files larger than 50 MB are rejected to prevent memory issues.
