#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="cross-build"
UNIT_FILE="$HOME/.config/systemd/user/$SERVICE_NAME.service"

if [ ! -f "$UNIT_FILE" ]; then
    echo "Service not installed."
    exit 0
fi

systemctl --user stop "$SERVICE_NAME" 2>/dev/null || true
systemctl --user disable "$SERVICE_NAME" 2>/dev/null || true
rm -f "$UNIT_FILE"
systemctl --user daemon-reload

echo "Service uninstalled."
