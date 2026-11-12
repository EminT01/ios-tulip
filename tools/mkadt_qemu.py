#!/usr/bin/env python3
"""tulip ADT'nin QEMU virt (GICv3 @0x08000000/0x080A0000, vtimer PPI 27) kopyasi."""
import struct, sys
src, dst = sys.argv[1], sys.argv[2]
SOC = 0x01000000
d = bytearray(open(src,'rb').read())
old = struct.pack('<4Q', 0x17a00000-SOC, 0x10000, 0x17b00000-SOC, 0x100000)
new = struct.pack('<4Q', 0x08000000-SOC, 0x10000, 0x080A0000-SOC, 0x0F6000)
assert d.count(old) == 1, f"gic reg eslesmedi ({d.count(old)})"
d = bytearray(bytes(d).replace(old, new))
i = d.find(b'virtual-timer-intid\x00')
struct.pack_into('<I', d, i+36, 27)
open(dst,'wb').write(bytes(d))
print(f"[+] {dst} ({len(d)} bytes)")
