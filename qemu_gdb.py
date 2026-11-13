#!/usr/bin/env python3
"""Run tulip payload in QEMU with a gdb stub, wait, then dump a backtrace."""
import os, struct, subprocess, sys, time

PAY, OUT = sys.argv[1], sys.argv[2]
SECS = float(sys.argv[3]) if len(sys.argv) > 3 else 60
KERN = sys.argv[4] if len(sys.argv) > 4 else 'kernel/kernel.development.vince'
FB, W, H, BPP = 0x9d400000, 1080, 2280, 4

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

pr = subprocess.Popen(['qemu-system-aarch64', '-M', 'virt,gic-version=3', '-cpu', 'cortex-a53',
                       '-smp', '1', '-m', '4G', '-nographic', '-no-reboot', '-gdb', 'tcp::1235',
                       '-device', f'loader,file={OUT}/ram.bin,addr={start:#x},force-raw=on',
                       '-device', f'loader,file={OUT}/stub.bin,addr=0x40200000,force-raw=on',
                       '-device', 'loader,addr=0x40200000,cpu-num=0'],
                      stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print(f'[*] qemu pid {pr.pid}, start={start:#x} entry={ent + delta:#x}', flush=True)
print(f'[*] running freely for {SECS:.0f}s', flush=True)
time.sleep(SECS)

gdb_cmds = f'''
set confirm off
set pagination off
set architecture aarch64
file {KERN}
target remote :1235
info registers pc sp x0 x1 x29 x30
bt
x/24i $pc-32
detach
quit
'''
open(f'{OUT}/gdb.cmd', 'w').write(gdb_cmds)
r = subprocess.run(['gdb-multiarch', '-batch', '-x', f'{OUT}/gdb.cmd'],
                   capture_output=True, text=True, timeout=SECS + 120)
print(r.stdout[-8000:])
print('--- stderr ---')
print(r.stderr[-3000:])
pr.kill()
