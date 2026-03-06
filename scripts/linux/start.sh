#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="cross-build"

systemctl --user start "$SERVICE_NAME"
systemctl --user status "$SERVICE_NAME" --no-pager
