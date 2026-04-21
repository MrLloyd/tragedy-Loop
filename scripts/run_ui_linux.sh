#!/usr/bin/env bash
set -euo pipefail

LIB_DIR="/tmp/tragedy-qt-libs/usr/lib/x86_64-linux-gnu"

if [ ! -d "$LIB_DIR" ]; then
  echo "Missing local Qt xcb runtime libs at $LIB_DIR" >&2
  echo "Download/extract the workaround packages first." >&2
  exit 1
fi

export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"
export LD_LIBRARY_PATH="$LIB_DIR${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

exec python3 main.py
