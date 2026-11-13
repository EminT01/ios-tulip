#!/bin/bash
set -e
cd "$(dirname "$0")"
FB=/mnt/c/platform-tools/fastboot.exe
IMG=${1:-shim-tulip/out/tulip-boot.img}
STAGE=/mnt/c/platform-tools/_boot.img
[ -f "$IMG" ] || { echo "imaj yok: $IMG"; exit 1; }
cp "$IMG" "$STAGE"
echo "[*] flash boot ($(( $(stat -c%s "$IMG")/1024/1024 )) MB)"
"$FB" flash boot "C:\\platform-tools\\_boot.img"
"$FB" reboot
rm -f "$STAGE"
