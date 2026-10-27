#!/bin/sh
# 背景啟動員工系統＋股東網站（macOS／Linux）。加 --demo 啟動示範店。
cd "$(dirname "$0")" && exec python3 -X utf8 tools/launcher.py start --open "$@"
