#!/usr/bin/env bash

LOG_DIR="$HOME/Library/Logs/cross-build"

if [ ! -d "$LOG_DIR" ]; then
    echo "No log directory found at $LOG_DIR"
    exit 1
fi

echo "=== stdout ==="
tail -f "$LOG_DIR/stdout.log" &
PID_OUT=$!

echo "=== stderr ==="
tail -f "$LOG_DIR/stderr.log" &
PID_ERR=$!

trap "kill $PID_OUT $PID_ERR 2>/dev/null" EXIT
wait
