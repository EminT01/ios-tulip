#!/usr/bin/env python3
"""Run QEMU and log which kernel symbols between LOCKDOWN phase and bsd_init are reached."""
import os, struct, subprocess, sys, time

PAY, OUT = sys.argv[1], sys.argv[2]
SECS = float(sys.argv[3]) if len(sys.argv) > 3 else 25
KERN = 'kernel/kernel.development.vince'
FB, W, H, BPP = 0x9d400000, 1080, 2280, 4
PORT = int(os.environ.get('GPORT', '1263'))
CAND = os.environ.get('CAND', 'oslog_stream_init,OSKextRemoveKextBootstrap,machine_lockdown,PE_lockdown_iokit,'
                             'vm_set_restrictions,kperf_init_early,bsd_init').split(',')

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
for pk in [s for s in os.environ.get('POKES', '').split(',') if s.strip()]:
    va_s, w_s = pk.split(':')
    off = int(va_s, 16) + delta - start
    assert 0 <= off < len(img) - 4, f'poke {va_s} outside image'
    img[off:off + 4] = struct.pack('<I', int(w_s, 16))
    print(f'[*] poke {va_s} -> {w_s}', flush=True)
os.makedirs(OUT, exist_ok=True)
open(f'{OUT}/ram.bin', 'wb').write(img)
open(f'{OUT}/stub.bin', 'wb').write(
    struct.pack('<4I2Q', 0x58000080, 0x580000a1, 0xd61f0020, 0xd503201f, ba_pa, ent + delta))

log = f'{OUT}/hits.log'
if os.path.exists(log):
    os.remove(log)
lines = ['set confirm off', 'set pagination off', 'set architecture aarch64',
         f'file {KERN}', f'target remote :{PORT}',
         f'set logging file {log}', 'set logging enabled on', 'set logging redirect on']
for c in CAND:
    spec = ('*' + c) if c.startswith('0x') else c
    body = [f'echo HIT {c}\\n']
    if os.environ.get('DUMPREGS'):
        body += ['printf "  pc=%#lx lr=%#lx x0=%#lx x1=%#lx x2=%#lx\\n", $pc, $x30, $x0, $x1, $x2']
    if os.environ.get('DUMPSTR'):
        body += ['x/s $x0']
    if os.environ.get('DUMPBT'):
        body += ['bt 25']
    for rg in [r for r in os.environ.get('DUMPX', '').split(',') if r.strip()]:
        body += [f'printf "  {rg}=%#lx\\n", ${rg}']
    lines += [f'break {spec}', 'commands', 'silent'] + body + ['continue', 'end']
lines += ['continue']
if os.environ.get('SETAT'):
    st = os.environ['SETAT']
    lines = lines[:-1] + [f'break *{st}', 'commands', 'silent'] + \
        [c for c in os.environ.get('SETCMDS', '').split(';;') if c] + ['continue', 'end', 'continue']
open(f'{OUT}/gdb3.cmd', 'w').write('\n'.join(lines) + '\n')

pr = subprocess.Popen(['qemu-system-aarch64', '-M', 'virt,gic-version=3', '-cpu', 'cortex-a53',
                       '-smp', '1', '-m', '4G', '-nographic', '-no-reboot', '-gdb', f'tcp::{PORT}',
                       '-device', f'loader,file={OUT}/ram.bin,addr={start:#x},force-raw=on',
                       '-device', f'loader,file={OUT}/stub.bin,addr=0x40200000,force-raw=on',
                       '-device', 'loader,addr=0x40200000,cpu-num=0'] + (['-S'] if os.environ.get('STARTSTOP') else []),
                      stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.0 if not os.environ.get('STARTSTOP') else 1.5)
g = subprocess.Popen(['gdb-multiarch', '-batch', '-x', f'{OUT}/gdb3.cmd'],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.PIPE, text=True)
print(f'[*] running {SECS:.0f}s with breakpoints: {CAND}', flush=True)
time.sleep(SECS)
g.kill()
pr.kill()
try:
    err = g.stderr.read()[:400]
except Exception:
    err = ''
time.sleep(0.3)
print('=== hits ===')
print(open(log).read() if os.path.exists(log) else '(no log)')
if err:
    print('--- gdb stderr ---')
    print(err)
