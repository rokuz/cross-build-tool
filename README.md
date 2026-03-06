# Cross-Platform Build Service

A lightweight Python service that lets you test code changes across macOS, Windows, and Linux machines on your local network. Services discover each other automatically, accept patches over HTTP, run builds in isolated git worktrees, and return logs to the initiator.

Includes a Claude Code skill so Claude can automatically verify fixes compile on all platforms and iterate until they pass.

## How it works

```
  Developer machine                 LAN                    Build machines
 +-----------------+                                  +-------------------+
 |  git diff HEAD  |  --- UDP discovery (5199) --->   | Linux service     |
 |  + new files    |  --- HTTP PATCH (5200) ------+-> | macOS service     |
 |                 |  <-- build logs + exit code --+  | Windows service   |
 +-----------------+                                  +-------------------+
```

1. Each machine runs the service, which broadcasts its presence via UDP every 3 seconds
2. From the dev machine you run `build` -- it collects your uncommitted changes and new files
3. The patch is sent to all (or selected) peers over HTTP
4. Each peer checks out the base commit in a **git worktree**, applies the patch, runs the configured build commands, and reports back
5. Results (logs, exit codes, pass/fail) are returned as JSON

## Requirements

- Python 3.9+
- `aiohttp` (only external dependency)
- `git` available in PATH on all machines
- All machines must have the **same repository cloned** and reachable at a known path
- Machines must be on the same local network (UDP broadcast must reach between them)

## Deployment

### 1. Clone the repo on every machine

```bash
# On each machine (macOS, Linux, Windows):
git clone <your-repo-url> /path/to/project
```

### 2. Install the service on every machine

```bash
cd /path/to/cross_platform_skill
python -m venv .venv

# Linux / macOS
source .venv/bin/activate

# Windows (cmd)
.venv\Scripts\activate.bat

# Windows (PowerShell)
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

### 3. Configure build commands in your project

Create `.cross_build/config.json` in the **target project's** repository root:

```bash
mkdir -p /path/to/project/.cross_build
```

```json
{
  "port": 5200,
  "build_commands": {
    "default": [
      "pip install -r requirements.txt",
      "python -m pytest"
    ],
    "linux": [
      "pip install -r requirements.txt",
      "python -m pytest",
      "make -j$(nproc)"
    ],
    "darwin": [
      "pip install -r requirements.txt",
      "python -m pytest",
      "xcodebuild -scheme MyApp -configuration Debug build"
    ],
    "windows": [
      "pip install -r requirements.txt",
      "python -m pytest",
      "msbuild MyProject.sln /p:Configuration=Release /p:Platform=x64"
    ]
  }
}
```

#### Config reference

| Field | Type | Default | Description |
|---|---|---|---|
| `port` | int | `5200` | HTTP API port for the service |
| `build_commands` | object or list | `{"default": []}` | Build commands per platform |

`build_commands` keys:

| Key | When used |
|---|---|
| `"default"` | Fallback -- used when no platform-specific entry matches |
| `"linux"` | Host runs Linux (`platform.system() == "Linux"`) |
| `"darwin"` | Host runs macOS (`platform.system() == "Darwin"`) |
| `"windows"` | Host runs Windows (`platform.system() == "Windows"`) |

Each value is a list of shell commands. They run sequentially in the worktree directory. The build stops on the first command that exits with a non-zero code.

The environment variable `CROSS_BUILD=1` is set during all builds, so your scripts can detect remote builds if needed.

### 4. Start the service on each machine

```bash
# Linux / macOS
cd /path/to/cross_platform_skill
source .venv/bin/activate
python -m cross_build serve --repo /path/to/project

# Windows (cmd)
cd C:\path\to\cross_platform_skill
.venv\Scripts\activate.bat
python -m cross_build serve --repo C:\path\to\project
```

You should see:

```
Cross-build service running on my-hostname (linux)
  HTTP port : 5200
  Repo      : /path/to/project
  Commands  : ['pip install -r requirements.txt', 'python -m pytest', 'make -j$(nproc)']
Press Ctrl+C to stop.
```

#### Running as a background service

Ready-made scripts are provided in `scripts/` for each platform. Every platform has: `install`, `uninstall`, `start`, `stop`, `status`, `logs`.

**Linux (systemd user service):**

```bash
# Install (creates ~/.config/systemd/user/cross-build.service)
./scripts/linux/install.sh /path/to/project 5200

# Manage
./scripts/linux/start.sh
./scripts/linux/stop.sh
./scripts/linux/status.sh
./scripts/linux/logs.sh

# Remove
./scripts/linux/uninstall.sh
```

**macOS (launchd user agent):**

```bash
# Install (creates ~/Library/LaunchAgents/com.cross-build.service.plist)
./scripts/darwin/install.sh /path/to/project 5200

# Manage
./scripts/darwin/start.sh
./scripts/darwin/stop.sh
./scripts/darwin/status.sh
./scripts/darwin/logs.sh

# Remove
./scripts/darwin/uninstall.sh
```

**Windows (Task Scheduler):**

```powershell
# Install (creates CrossBuildService scheduled task)
.\scripts\windows\install.ps1 -RepoPath C:\path\to\project -Port 5200

# Manage
.\scripts\windows\start.ps1
.\scripts\windows\stop.ps1
.\scripts\windows\status.ps1
.\scripts\windows\logs.ps1

# Remove
.\scripts\windows\uninstall.ps1
```

All install scripts automatically create the `.venv` and install dependencies if needed.

## Usage

### Discover peers

```bash
python -m cross_build discover --timeout 5
```

Output:
```json
[
  {
    "hostname": "linux-box",
    "platform": "linux",
    "ip": "192.168.1.10",
    "port": 5200
  },
  {
    "hostname": "win-pc",
    "platform": "windows",
    "ip": "192.168.1.11",
    "port": 5200
  }
]
```

### Build on all platforms

```bash
python -m cross_build build --repo /path/to/project
```

### Build on specific platforms

```bash
python -m cross_build build --repo /path/to/project --to linux,windows
```

### Build with custom commands (overrides config)

```bash
python -m cross_build build --repo /path/to/project \
  --cmd "pip install -r requirements.txt" \
  --cmd "python -m pytest tests/test_core.py -v"
```

### Check a specific build result

```bash
python -m cross_build result <build_id> --host 192.168.1.10 --port 5200
```

### Build output example

```json
{
  "results": [
    {
      "platform": "linux",
      "hostname": "linux-box",
      "id": "a1b2c3d4",
      "status": "success",
      "logs": "$ pip install -r requirements.txt\n...\n$ python -m pytest\n===== 42 passed =====\n$ make -j8\n...\n",
      "exit_code": 0
    },
    {
      "platform": "windows",
      "hostname": "win-pc",
      "id": "e5f6g7h8",
      "status": "failed",
      "logs": "$ pip install -r requirements.txt\n...\n$ python -m pytest\nFAILED tests/test_path.py::test_separator\n...\nCommand failed with exit code 1",
      "exit_code": 1
    }
  ]
}
```

The process exits with code 0 only if **all** builds succeed.

## Claude Code skill

The included Claude Code skill teaches Claude to use the cross-build service automatically. When enabled, you can ask Claude things like "check if this compiles on Windows and Linux" and it will discover peers, send your changes, read logs, fix issues, and retry -- all without manual intervention.

### How Claude Code skills work

Claude Code loads skill files from `.claude/skills/` directories. When Claude sees a task that matches a skill's description, it follows the instructions in the skill file. Skills are just markdown files with a YAML frontmatter header.

### Option A: Per-project skill (recommended)

Install the skill into any project where you want cross-platform build support:

```bash
# From your target project's root
mkdir -p .claude/skills

# Copy the skill file
cp /path/to/cross_platform_skill/.claude/skills/cross-build.md .claude/skills/
```

The skill file will be picked up automatically next time you start Claude Code in that project. You can commit it to version control so the whole team gets it.

### Option B: Global skill (all projects)

Install the skill globally so it's available in every project:

```bash
mkdir -p ~/.claude/skills
cp /path/to/cross_platform_skill/.claude/skills/cross-build.md ~/.claude/skills/
```

### Verify the skill is loaded

Start Claude Code in your project and ask:

```
> What skills do you have?
```

You should see `cross-build` listed.

### Usage examples

Once the skill is enabled and the services are running on your build machines:

```
> Check if my changes build on Linux and Windows

> Run the tests on all platforms

> I fixed the path separator issue, verify it passes on Windows now

> Build on darwin only
```

Claude will:

1. Run `python -m cross_build discover` to find available peers
2. Run `python -m cross_build build --repo . --to <platforms>` to send your uncommitted changes
3. Parse the JSON output for pass/fail status and logs
4. If a build fails -- read the error logs, identify platform-specific issues (path separators, missing headers, API differences, etc.), fix the code, and re-run the build
5. Repeat until all platforms report `"status": "success"`

### What the skill file contains

The skill file (`.claude/skills/cross-build.md`) tells Claude:

- **When to activate** -- user asks about cross-platform testing/building
- **CLI commands** -- exact `python -m cross_build` invocations to run
- **Output format** -- how to parse the JSON results
- **Fix-and-retry loop** -- how to iterate on failures
- **Configuration** -- where `.cross_build/config.json` lives and what it contains

You can edit the skill file to customize behavior, for example to always target specific platforms or to add pre-build steps.

## CLI reference

| Command | Description |
|---|---|
| `python -m cross_build serve` | Start the build service |
| `python -m cross_build discover` | Find peers on the network |
| `python -m cross_build build` | Send changes to peers for building |
| `python -m cross_build result <id> --host <ip>` | Fetch a build result |

### `serve` options

| Flag | Default | Description |
|---|---|---|
| `--repo PATH` | current directory | Path to the git repository |
| `--port PORT` | 5200 | HTTP API port |
| `--config PATH` | `.cross_build/config.json` | Config file path |
| `-v, --verbose` | off | Debug logging |

### `build` options

| Flag | Default | Description |
|---|---|---|
| `--repo PATH` | current directory | Path to the git repository |
| `--to PLATFORMS` | all discovered | Comma-separated: `linux,windows,darwin` |
| `--cmd COMMAND` | from config | Build command (repeatable) |
| `--timeout SECONDS` | 300 | Max wait time per build |

## Network details

- **Discovery:** UDP broadcast on port **5199** (every 3s, peers expire after 15s)
- **API:** HTTP on port **5200** (configurable)
- All machines must be on the same broadcast domain (same LAN / subnet)

## Troubleshooting

| Problem | Fix |
|---|---|
| No peers discovered | Check firewall allows UDP 5199 and TCP 5200. Verify machines are on the same subnet. |
| "Base commit not found" | Run `git fetch` / `git pull` on the target machine so it has the latest commits. |
| "Failed to create worktree" | Ensure the repo path is correct and git is available. Check disk space. |
| Build timeout | Increase with `--timeout`. Check if the build command hangs. |
| Large patches fail | Default upload limit is 50MB. Avoid committing large binaries. |

## License

[MIT](LICENSE)
