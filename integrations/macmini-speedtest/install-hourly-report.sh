#!/bin/sh
# Compatibility entry point; hourly Telegram messages have been superseded.
set -eu
cd "$(dirname "$0")"
exec python3 -B install-chart-reports.py
