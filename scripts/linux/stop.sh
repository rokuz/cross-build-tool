#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="cross-build"

systemctl --user stop "$SERVICE_NAME"
echo "Service stopped."
