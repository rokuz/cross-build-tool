import json
import os

CONFIG_DIR = ".cross_build"
CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "port": 5200,
    "discovery_port": 5199,
    "build_commands": {"default": []},
}

# Expected config format (.cross_build/config.json):
#
# {
#   "port": 5200,
#   "build_commands": {
#     "default": ["python -m pytest"],
#     "linux": ["python -m pytest", "make"],
#     "darwin": ["python -m pytest", "xcodebuild -scheme App"],
#     "windows": ["python -m pytest", "msbuild project.sln /p:Configuration=Release"]
#   }
# }
#
# "build_commands" keys:
#   "default"  - fallback used when no platform-specific entry exists
#   "linux"    - commands to run on Linux
#   "darwin"   - commands to run on macOS
#   "windows"  - commands to run on Windows
#
# Each value is a list of shell commands executed sequentially.
# Build stops on the first command that returns a non-zero exit code.


def load_config(config_path=None, repo_path=None):
    if config_path and os.path.exists(config_path):
        with open(config_path) as f:
            return {**DEFAULT_CONFIG, **json.load(f)}

    if repo_path:
        default_path = os.path.join(repo_path, CONFIG_DIR, CONFIG_FILE)
        if os.path.exists(default_path):
            with open(default_path) as f:
                return {**DEFAULT_CONFIG, **json.load(f)}

    return DEFAULT_CONFIG.copy()
