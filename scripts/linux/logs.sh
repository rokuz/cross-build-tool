#!/usr/bin/env bash

SERVICE_NAME="cross-build"

journalctl --user -u "$SERVICE_NAME" -f --no-pager "${@}"
