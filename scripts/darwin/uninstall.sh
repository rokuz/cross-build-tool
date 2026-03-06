#!/usr/bin/env bash
set -euo pipefail

LABEL="com.cross-build.service"
PLIST_FILE="$HOME/Library/LaunchAgents/$LABEL.plist"

if [ ! -f "$PLIST_FILE" ]; then
    echo "Service not installed."
    exit 0
fi

launchctl bootout "gui/$(id -u)" "$PLIST_FILE" 2>/dev/null || true
rm -f "$PLIST_FILE"

echo "Service uninstalled."
