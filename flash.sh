#!/bin/bash
set -e
cd "$(dirname "$0")"
FB=/mnt/c/platform-tools/fastboot.exe
IMG=${1:-shim-tulip/out/tulip-boot.img}
STAGE=/mnt/c/platform-tools/_boot.img
cp "$IMG" "$STAGE"
"$FB" flash boot "C:\\platform-tools\\_boot.img"
"$FB" reboot
rm -f "$STAGE"
