#!/bin/sh
cd "$(dirname "$0")" && exec python3 -X utf8 tools/launcher.py stop "$@"
