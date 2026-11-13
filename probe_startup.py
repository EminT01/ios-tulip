#!/usr/bin/env python3
"""Halt the VM and read startup_phase / startup_entry_cur to find the last startup hook run."""
import bisect, os, struct, subprocess, sys, time

PAY, OUT = sys.argv[1], sys.argv[2]
SECS = float(sys.argv[3]) if len(sys.argv) > 3 else 20
KERN = 'kernel/kernel.development.vince'
FB, W, H, BPP = 0x9d400000, 1080, 2280, 4
PORT = int(os.environ.get('GPORT', '1247'))

p = open(PAY, 'rb').read()
ns = struct.unpack_from('<I', p, 12)[0]
virt, ent, ao, asz, ke, pb, ms = struct.unpack_from('<7Q', p, 0x10)
PG = 0x1000
delta = pb - virt
adt_pa = ke + delta
ba_pa = (adt_pa + asz + PG - 1) & ~(PG - 1)
top = ba_pa + PG
sps = [struct.unpack_from('<4Q', p, 0x2a8 + 32 * i)[0] + delta for i in range(ns)]
start = min(sps + [pb]) & ~(PG - 1)
img = bytearray(top - start)
for i in range(ns):
    vm, vs, fo, fs = struct.unpack_from('<4Q', p, 0x2a8 + 32 * i)
    img[vm + delta - start:vm + delta - start + fs] = p[fo:fo + fs]
img[adt_pa - start:adt_pa - start + asz] = p[ao:ao + asz]
cmd = p[0x48:0x48 + 608]
ba = struct.pack('<HH4x4Q6QI4xQI', 2, 2, virt, pb, ms, top, FB, 1, W * BPP, W, H, 32, 0, adt_pa, asz)
ba += cmd + b'\0' * 4 + struct.pack('<2Q', 0, ms)
img[ba_pa - start:ba_pa - start + len(ba)] = ba
os.makedirs(OUT, exist_ok=True)
open(f'{OUT}/ram.bin', 'wb').write(img)
open(f'{OUT}/stub.bin', 'wb').write(
    struct.pack('<4I2Q', 0x58000080, 0x580000a1, 0xd61f0020, 0xd503201f, ba_pa, ent + delta))

# symbol table
nm = subprocess.run(['llvm-nm', '-C', '--defined-only', KERN], capture_output=True, text=True).stdout
sym = {}
addrs = []
for l in nm.splitlines():
    q = l.split(maxsplit=2)
    if len(q) == 3:
        try:
            a = int(q[0], 16)
        except ValueError:
            continue
        sym[a] = q[2]
        addrs.append(a)
addrs.sort()

def name_of(a):
    i = bisect.bisect_right(addrs, a) - 1
    if i < 0 or a - addrs[i] > 0x4000:
        return None
    return f'{sym[addrs[i]]}+{a - addrs[i]:#x}'

def addr(n):
    for a, s in sym.items():
        if s == n or s == '_' + n:
            return a
    raise SystemExit(f'symbol {n} not found')

A_phase = addr('startup_phase')
A_cur = addr('startup_entry_cur')
# __DATA,__init_entry_set section (struct startup_entry[])
A_ents = int(os.environ.get('ENTS', '0xfffffff00891ce68'), 16)
ESIZE = int(os.environ.get('ESIZE', '0x17eb0'), 16)
A_end = A_ents + ESIZE
A_dbg = addr('startup_debug')
print(f'[*] phase={A_phase:#x} cur={A_cur:#x} ents={A_ents:#x}..{A_end:#x}', flush=True)

pr = subprocess.Popen(['qemu-system-aarch64', '-M', 'virt,gic-version=3', '-cpu', 'cortex-a53',
                       '-smp', '1', '-m', '4G', '-nographic', '-no-reboot', '-gdb', f'tcp::{PORT}',
                       '-device', f'loader,file={OUT}/ram.bin,addr={start:#x},force-raw=on',
                       '-device', f'loader,file={OUT}/stub.bin,addr=0x40200000,force-raw=on',
                       '-device', 'loader,addr=0x40200000,cpu-num=0'],
                      stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print(f'[*] running {SECS:.0f}s', flush=True)
time.sleep(SECS)

gdb = f'''set confirm off
set pagination off
set architecture aarch64
file {KERN}
target remote :{PORT}
x/1wx {A_phase:#x}
x/1wx {A_dbg:#x}
x/1gx {A_cur:#x}
dump binary memory {OUT}/entries.bin {A_ents:#x} {A_end:#x}
info registers pc
bt
detach
quit
'''
open(f'{OUT}/gdb2.cmd', 'w').write(gdb)
r = subprocess.run(['gdb-multiarch', '-batch', '-x', f'{OUT}/gdb2.cmd'],
                   capture_output=True, text=True, timeout=90)
print(r.stdout)
pr.kill()

raw = open(f'{OUT}/entries.bin', 'rb').read()
n = len(raw) // 24
ents = []
for i in range(n):
    func, arg = struct.unpack_from('<QQ', raw, i * 24)
    sub, rank = struct.unpack_from('<BB', raw, i * 24 + 16)
    ents.append((func, arg, sub, rank))
print(f'[*] {n} startup entries (24B each)')

import re
txt = r.stdout
phase = cur = dbg = None
for l in txt.splitlines():
    if ':' not in l or not l.startswith('0x'):
        continue
    atok = l.split()[0]
    try:
        a = int(atok, 16)
    except ValueError:
        continue
    v = l.split(':', 1)[1].split()[0]
    if a == A_phase:
        phase = int(v, 16)
    elif a == A_dbg:
        dbg = int(v, 16)
    elif a == A_cur:
        cur = int(v, 16)
print(f'[*] startup_phase={phase!r} startup_debug={dbg!r} entry_cur={cur!r}')
if cur:
    idx = (cur - A_ents) // 24
    print(f'[*] startup_entry_cur -> index {idx} (of {n})')
    for j in range(max(0, idx - 3), min(n, idx + 2)):
        f_, a_, s_, r_ = ents[j]
        print(f'    [{">" if j == idx else " "}{j}] sub={s_} rank={r_} func={name_of(f_) or hex(f_)}')
uidx = None
if cur:
    uidx = (cur - A_ents) // 24 - 1
    if 0 <= uidx < n:
        f_, a_, s_, r_ = ents[uidx]
        print(f'[*] LAST EXECUTED HOOK: sub={s_} rank={r_} func={name_of(f_) or hex(f_)}')
