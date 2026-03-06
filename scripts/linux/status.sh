#!/usr/bin/env bash

SERVICE_NAME="cross-build"

systemctl --user status "$SERVICE_NAME" --no-pager 2>/dev/null || echo "Service not running or not installed."
