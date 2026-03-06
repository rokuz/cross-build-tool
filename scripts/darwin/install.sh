#!/usr/bin/env bash
set -euo pipefail

# Install cross-build as a launchd user agent on macOS.
# Usage: ./install.sh /path/to/project [port]

REPO_PATH="${1:?Usage: $0 /path/to/project [port]}"
PORT="${2:-5200}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PKG_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
VENV_DIR="$PKG_DIR/.venv"
LABEL="com.cross-build.service"
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST_FILE="$PLIST_DIR/$LABEL.plist"
LOG_DIR="$HOME/Library/Logs/cross-build"

# Resolve absolute path
REPO_PATH="$(cd "$REPO_PATH" && pwd)"

# Ensure venv exists
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating venv at $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --quiet -r "$PKG_DIR/requirements.txt"
fi

mkdir -p "$PLIST_DIR" "$LOG_DIR"

cat > "$PLIST_FILE" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$VENV_DIR/bin/python</string>
        <string>-m</string>
        <string>cross_build</string>
        <string>serve</string>
        <string>--repo</string>
        <string>$REPO_PATH</string>
        <string>--port</string>
        <string>$PORT</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$PKG_DIR</string>
    <key>RunAtLoad</key>
    <false/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>StandardOutPath</key>
    <string>$LOG_DIR/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>$LOG_DIR/stderr.log</string>
</dict>
</plist>
EOF

echo "Installed: $PLIST_FILE"
echo "  Repo: $REPO_PATH"
echo "  Port: $PORT"
echo "  Logs: $LOG_DIR"
echo ""
echo "Run: scripts/darwin/start.sh"
