#!/usr/bin/env bash

LABEL="com.cross-build.service"
LOG_DIR="$HOME/Library/Logs/cross-build"

echo "=== Service status ==="
launchctl print "gui/$(id -u)/$LABEL" 2>/dev/null || echo "Service not running or not installed."

echo ""
echo "=== Recent logs ==="
if [ -f "$LOG_DIR/stderr.log" ]; then
    tail -20 "$LOG_DIR/stderr.log"
else
    echo "No logs yet."
fi
