# Cross-Platform Build Service

Python service for testing code changes across macOS, Windows, and Linux on a local network.

## Setup

```bash
pip install -r requirements.txt
```

## Usage

### Run the service (on each machine)

```bash
python -m cross_build serve --repo /path/to/repo --port 5200
```

### Discover peers

```bash
python -m cross_build discover
```

### Send changes for remote building

```bash
python -m cross_build build --repo /path/to/repo --to linux,windows
```

## Project structure

- `cross_build/discovery.py` - UDP broadcast peer discovery (port 5199)
- `cross_build/server.py` - aiohttp HTTP API server
- `cross_build/client.py` - Client: discover peers, send patches, collect results
- `cross_build/patcher.py` - Creates git diff + collects new files
- `cross_build/builder.py` - Applies patches in git worktrees and runs builds
- `cross_build/config.py` - Loads `.cross_build/config.json`
- `cross_build/__main__.py` - CLI entry point

## Configuration

Create `.cross_build/config.json` in your repo:

```json
{
  "build_commands": {
    "default": ["python -m pytest"],
    "windows": ["msbuild project.sln /p:Configuration=Release"],
    "linux": ["python -m pytest", "make"],
    "darwin": ["python -m pytest", "xcodebuild -scheme App"]
  }
}
```

Keys under `build_commands`:
- `"default"` - fallback when no platform-specific entry exists
- `"linux"` / `"darwin"` / `"windows"` - platform-specific commands

Commands run sequentially; build stops on first non-zero exit code.
