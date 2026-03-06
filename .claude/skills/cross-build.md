---
name: cross-build
description: Test code changes on other platforms (macOS, Windows, Linux) via the cross-build network service.
---

# Cross-Platform Build Testing

Use this skill when the user wants to verify builds pass on other operating systems.

## Prerequisites

The `cross_build` service must be running on target machines:
```
python -m cross_build serve --repo /path/to/repo
```

## Workflow

### 1. Send changes for building

```bash
# Build on all OTHER platforms (auto-detects current, sends to the rest)
python -m cross_build build --repo /path/to/repo

# Build on specific platforms only
python -m cross_build build --repo /path/to/repo --to linux,windows

# Custom build commands
python -m cross_build build --repo /path/to/repo --cmd "pip install -r requirements.txt" --cmd "python -m pytest"
```

The command automatically:
- Detects the current platform (linux/windows/darwin)
- Discovers peers on OTHER platforms only (skips same-platform peers)
- Reports platform coverage: which of the 3 platforms are covered and which are missing

Exit code is 0 only if ALL builds succeed.

### 2. Analyze results

Output JSON includes:
- `current_platform`: the platform you're running on
- `coverage`: which platforms are covered and which are missing
  - `all_covered`: true when linux + windows + darwin are all accounted for
  - `missing`: list of platforms with no service discovered
- `results`: array with `platform`, `hostname`, `status`, `logs`, `exit_code` per target

Check `coverage.all_covered` -- if false, warn the user about missing platforms.
Check each result's `status` -- "success" means pass, "failed"/"error" means problems.

### 3. Fix and retry

If builds fail:
1. Read error logs for platform-specific issues (path separators, missing headers, API differences)
2. Fix the code
3. Re-run `python -m cross_build build`
4. Repeat until all platforms report `"status": "success"`

### Optional: discover peers only

```bash
python -m cross_build discover --timeout 5
```

Returns JSON listing all peers (useful for debugging connectivity).

## Configuration

Projects use `.cross_build/config.json` in the repo root:
```json
{
  "build_commands": {
    "default": ["python -m pytest"],
    "windows": ["python -m pytest tests\\"],
    "linux": ["python -m pytest", "make check"],
    "darwin": ["python -m pytest", "xcodebuild -scheme App"]
  }
}
```

Keys: `"default"` (fallback), `"linux"`, `"darwin"`, `"windows"`. Commands run sequentially, stopping on first failure.

## Notes

- Builds use git worktrees (don't disturb local work on target machines)
- All machines need the same repo cloned with the base commit available
- `CROSS_BUILD=1` env var is set during builds
- Default timeout is 300s, override with `--timeout`
