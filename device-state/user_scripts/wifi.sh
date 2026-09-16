#!/bin/sh
set -eu
cd "$(dirname "$0")/wifi-app"
export QT_QPA_PLATFORM=eglfs
exec /usr/bin/python3 ./wifi.py
