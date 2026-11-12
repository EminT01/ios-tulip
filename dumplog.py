#!/usr/bin/env python3
"""QEMU ramdump.bin icinden kernel console logunu cikar.
Iki yol: (1) debug_buf pointer'ini takip et, (2) panic/console ring'i ara."""
import struct, subprocess, sys, re

dump = sys.argv[1] if len(sys.argv) > 1 else 'qemu-vb2/ramdump.bin'
K    = sys.argv[2] if len(sys.argv) > 2 else 'kernel/kernel.development.vince'
d = open(dump, 'rb').read()
PBASE = 0xa0400000
print(f"dump: {len(d)//1024//1024} MB @ {PBASE:#x}")

# sembol adresleri
nm = subprocess.run(["llvm-nm","-n","--defined-only",K], capture_output=True, text=True).stdout
sym = {}
for l in nm.splitlines():
    p = l.split()
    if len(p) == 3:
        sym[p[2]] = int(p[0], 16)

def read64(va):
    # dump'taki fiziksel karsiligi: PA = va - virtbase + pbase; virtbase kernel'den
    for vb in (0xfffffff006000000, 0xfffffff007000000):
        pa = va - vb + PBASE
        o = pa - PBASE
        if 0 <= o < len(d) - 8:
            return struct.unpack_from('<Q', d, o)[0]
    return None

# 1) debug_buf pointer'ini takip et
for name in ('_debug_buf_base', '_debug_buf_ptr', '_debug_buf_size'):
    if name in sym:
        v = read64(sym[name])
        print(f"{name} @{sym[name]:#x} -> {v if v is None else hex(v)}")

base = read64(sym['_debug_buf_base']) if '_debug_buf_base' in sym else None
size = read64(sym['_debug_buf_size']) if '_debug_buf_size' in sym else 0
if base and base > 0xfffffff000000000:
    pa = base - 0xfffffff006000000 + PBASE
    o = pa - PBASE
    if 0 <= o < len(d):
        n = min(size or 0x40000, 0x20000)
        txt = d[o:o+n].split(b'\x00')[0].decode('latin1','replace')
        print("\n=== DEBUG BUF ===")
        print(txt)
    else:
        print(f"\ndebug_buf disarida (off={o:#x})")

# 2) yedek: 'bsd_init:' / 'virtio-blk:' gibi canli satirlari ara
print("\n=== metin aramasi ===")
for probe in (b'virtio-blk:', b'cannot mount root', b'setconf: IOFindBSDRoot',
              b'vfs_mountroot:', b'mountroot failed', b'root_device'):
    i = d.find(probe)
    print(f"  {probe.decode():28s} {'-> @'+hex(i) if i>=0 else '-> YOK'}")
