#!/usr/bin/env python3
"""Boot the payload in QEMU and trace which kernel milestones are reached."""
import os, struct, subprocess, sys, time

PAY, OUT = sys.argv[1], sys.argv[2]
SECS = float(sys.argv[3]) if len(sys.argv) > 3 else 45
KERN = 'kernel/kernel.development.vince'
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
                       '-smp', '1', '-m', '4G', '-nographic', '-no-reboot', '-gdb', 'tcp::1236',
                       '-device', f'loader,file={OUT}/ram.bin,addr={start:#x},force-raw=on',
                       '-device', f'loader,file={OUT}/stub.bin,addr=0x40200000,force-raw=on',
                       '-device', 'loader,addr=0x40200000,cpu-num=0'],
                      stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(SECS)

marks = ['kernel_bootstrap_thread', 'sched_startup', 'mapping_adjust', 'clock_service_create',
         'device_service_create', 'PE_init_iokit', 'trust_cache_runtime_init', 'bsd_init',
         'bsd_autoconf', 'vfs_mountroot', 'bsd_init_task', 'bsdinit_task', 'load_init_program',
         'panic', 'kminit', 'IOFindBSDRoot', 'sweet_ufs_rootdev', 'IOService::start',
         'configure_system_workqueue']
nm = subprocess.run(['llvm-nm', '--defined-only', KERN], capture_output=True, text=True).stdout
present = set()
for l in nm.splitlines():
    q = l.split(maxsplit=2)
    if len(q) == 3:
        present.add(q[2])
marks = [m for m in marks if m in present]
print('[*] symbols found:', marks, flush=True)

lines = ['set confirm off', 'set pagination off', 'set architecture aarch64',
         f'file {KERN}', 'target remote :1236']
for m in marks:
    lines.append(f'break {m}')
    lines.append(f'commands {m}')
    lines.append('silent')
    lines.append(f'printf "HIT {m}\\n"')
    lines.append('continue')
    lines.append('end')
lines += ['continue', 'shell sleep 8', 'info threads', 'bt', 'detach', 'quit']
open(f'{OUT}/gdb.cmd', 'w').write('\n'.join(lines) + '\n')
r = subprocess.run(['gdb-multiarch', '-batch', '-x', f'{OUT}/gdb.cmd'],
                   capture_output=True, text=True, timeout=SECS + 180)
out = r.stdout
hits = [l for l in out.splitlines() if l.startswith('HIT ')]
print('=== milestones reached ===')
for h in dict.fromkeys(hits):
    print('  ', h)
print('\n=== tail of gdb output ===')
print(out[-2500:])
print('--- stderr ---')
print(r.stderr[-1500:])
pr.kill()
