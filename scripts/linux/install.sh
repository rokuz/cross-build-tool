#!/usr/bin/env bash
set -euo pipefail

# Install cross-build as a systemd user service on Linux.
# Usage: ./install.sh /path/to/project [port]

REPO_PATH="${1:?Usage: $0 /path/to/project [port]}"
PORT="${2:-5200}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PKG_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
VENV_DIR="$PKG_DIR/.venv"
SERVICE_NAME="cross-build"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT_FILE="$UNIT_DIR/$SERVICE_NAME.service"

# Resolve absolute path
REPO_PATH="$(cd "$REPO_PATH" && pwd)"

# Ensure venv exists
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating venv at $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --quiet -r "$PKG_DIR/requirements.txt"
fi

# Create systemd user unit
mkdir -p "$UNIT_DIR"
cat > "$UNIT_FILE" <<EOF
[Unit]
Description=Cross-Platform Build Service
After=network.target

[Service]
Type=simple
WorkingDirectory=$PKG_DIR
ExecStart=$VENV_DIR/bin/python -m cross_build serve --repo $REPO_PATH --port $PORT
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable "$SERVICE_NAME"

echo "Installed: $UNIT_FILE"
echo "  Repo: $REPO_PATH"
echo "  Port: $PORT"
echo ""
echo "Run: scripts/linux/start.sh"
