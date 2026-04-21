#!/usr/bin/env bash
set -euo pipefail

DEB_DIR="/tmp/tragedy-qt-debs"
LIB_ROOT="/tmp/tragedy-qt-libs"

mkdir -p "$DEB_DIR" "$LIB_ROOT"

cd "$DEB_DIR"
apt-get download \
  libxcb-cursor0 \
  libxkbcommon-x11-0 \
  libxcb-icccm4 \
  libxcb-util1 \
  libxcb-image0 \
  libxcb-keysyms1 \
  libxcb-render-util0 \
  libxcb-xkb1

for pkg in ./*.deb; do
  dpkg-deb -x "$pkg" "$LIB_ROOT"
done

echo "Local Qt xcb runtime libs extracted to: $LIB_ROOT/usr/lib/x86_64-linux-gnu"
