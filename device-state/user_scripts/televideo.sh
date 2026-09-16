#!/bin/sh
set -eu
cd "$(dirname "$0")/televideo-app"
export QT_QPA_PLATFORM=eglfs
exec /usr/bin/python3 ./televideo.py
