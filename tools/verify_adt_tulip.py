#!/usr/bin/env python3
"""Sanity checks for the tulip ADT against the values measured on the phone."""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adt

RAM = [(0x40000000, 0x855fffff), (0x88f00000, 0x8abfffff), (0x94b00000, 0xfeabffff)]
FB = (0x9d400000, 0x9d400000 + 36 * 1024 * 1024 - 1)
RAMOOPS = (0xa0000000, 0xa03fffff)

def P(node):
    return {(k.rstrip(b'\0').decode() if isinstance(k, bytes) else k): v for k, _, v in node.props}

def main(path):
    root, _ = adt.parse(open(path, 'rb').read())
    rp = P(root)
    kids = {P(c)['name'].rstrip(b'\0').decode(): c for c in root.children}
    ok = True
    def check(cond, msg):
        nonlocal ok
        print(('[PASS] ' if cond else '[FAIL] ') + msg)
        ok &= bool(cond)
    ch = P(kids['chosen'])
    base, size = struct.unpack('<Q', ch['dram-base'])[0], struct.unpack('<Q', ch['dram-size'])[0]
    end = base + size - 1
    check(any(a <= base and end <= b for a, b in RAM), f'DRAM 0x{base:x}-0x{end:x} is inside one RAM bank')
    check(end < FB[0] or base > FB[1], 'DRAM does not overlap the splash framebuffer')
    check(end < RAMOOPS[0] or base > RAMOOPS[1], 'DRAM does not overlap ramoops')
    check(base % 0x200000 == 0, 'DRAM base is 2 MiB aligned')
    io = kids['arm-io']; soc = struct.unpack('<3Q', P(io)['ranges'])[1]
    gic = P({c.name: c for c in io.children}['gic'] if False else [c for c in io.children if P(c)['name'].rstrip(b'\0') == b'gic'][0])
    gd, gds, gr, grs = struct.unpack('<4Q', gic['reg'])
    check(soc + gd == 0x17a00000 and soc + gr == 0x17b00000, f'GICD/GICR = 0x{soc+gd:x}/0x{soc+gr:x}')
    check(struct.unpack('<I', gic['virtual-timer-intid'])[0] == 19, 'virtual timer INTID 19')
    fb = P(kids['vince-fbcon'])
    r = struct.unpack('<2Q', fb['reg'])
    check(r[0] >= FB[0] and r[0] + r[1] - 1 <= FB[1] and struct.unpack('<I', fb['bpp'])[0] == 32, 'fbcon inside LK splash FB, 32 bpp')
    check(struct.unpack('<I', fb['stride'])[0] == 4320, 'fbcon stride 4320')
    cpus = kids['cpus']
    check(len(cpus.children) == 8, f'8 cpu nodes ({len(cpus.children)})')
    regs = sorted(struct.unpack('<I', P(c)['reg'])[0] for c in cpus.children)
    want = [0, 1, 2, 3, 0x100, 0x101, 0x102, 0x103]
    check(regs == want, 'cpu regs are MPIDR 0x000-0x003 and 0x100-0x103')
    ids = sorted(struct.unpack('<I', P(c)['cpu-id'])[0] for c in cpus.children)
    check(ids == list(range(8)), 'cpu-id 0..7 contiguous')
    print('[OK]' if ok else '[BAD]')
    return 0 if ok else 1

if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
