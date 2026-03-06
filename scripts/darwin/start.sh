#!/usr/bin/env bash
set -euo pipefail

LABEL="com.cross-build.service"
PLIST_FILE="$HOME/Library/LaunchAgents/$LABEL.plist"

if [ ! -f "$PLIST_FILE" ]; then
    echo "Service not installed. Run install.sh first."
    exit 1
fi

launchctl bootstrap "gui/$(id -u)" "$PLIST_FILE" 2>/dev/null || \
    launchctl kickstart "gui/$(id -u)/$LABEL"

echo "Service started. Check status with: scripts/darwin/status.sh"
