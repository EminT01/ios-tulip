#!/bin/bash
set -e
cd "$(dirname "$0")"
KERNEL=${KERNEL:-kernel/kernel.development.vince}
CMDLINE=${CMDLINE:-"serial=3 cpus=1 keepsyms=1 -noprogress wdt=-1"}
python3 -I tools/mkpayload_tulip.py "$KERNEL" out/tulip.adt out/tulip.payload \
    --trustcache tc.bin --cmdline "$CMDLINE" | tail -3
python3 shim-tulip/build.py stock-boot.img shim-tulip/tools out/tulip.payload
./flash.sh
