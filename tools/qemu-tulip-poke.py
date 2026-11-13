#!/usr/bin/env python3
"""Boot the QEMU tulip payload with in-RAM kernel text pokes.

POKES="0xfffffff007485060:d65f03c0,..."  (VA:32-bit-word) patch guest RAM afte
image build, so a kernel change can be validated without a rebuild.
Usage: qemu-tulip-poke.py PAYLOAD OUTDIR [--secs N]
"""
import argparse, importlib.util, os, struct, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('qt', os.path.join(HERE, 'qemu-tulip.py'))
qt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('payload')
    ap.add_argument('outdir')
    ap.add_argument('--secs', type=float, default=40)
    ap.add_argument('--mem', default=None)
    a = ap.parse_args()

    payload = open(a.payload, 'rb').read()
    os.makedirs(a.outdir, exist_ok=True)
    out = os.path.abspath(a.outdir)
    virt_base, _, _, _, _, phys_base, mem_size = struct.unpack_from('<7Q', payload, 0x10)
    delta = phys_base - virt_base

    img_start, img, ba_pa, entry_pa = qt.build_image(payload)
    img = bytearray(img)
    specs = [s for s in os.environ.get('POKES', '').split(',') if s.strip()]
    for s in specs:
        va_s, w_s = s.split(':')
        va, w = int(va_s, 16), int(w_s, 16)
        off = va + delta - img_start
        assert 0 <= off < len(img) - 4, f'poke {va:#x} outside image'
        img[off:off + 4] = struct.pack('<I', w)
        print(f'poke {va:#x} -> {w:#010x} (pa {va + delta:#x})', file=sys.stderr)
    open(f'{out}/ram.bin', 'wb').write(bytes(img))
    open(f'{out}/stub.bin', 'wb').write(qt.stub(ba_pa, entry_pa))

    mon = f'{out}/mon.sock'
    if os.path.exists(mon):
        os.unlink(mon)
    if a.mem:
        ram = a.mem
    else:
        ram_gib = max(4, -(-(img_start + mem_size - 0x40000000) // (1 << 30)))
        ram = f'{ram_gib}G'
    cmd = ['qemu-system-aarch64', '-M', 'virt,gic-version=3', '-cpu', 'cortex-a53', '-smp', '1',
           '-m', ram, '-nographic', '-serial', f'file:{out}/serial.txt',
           '-qmp', f'unix:{mon},server,nowait', '-no-reboot',
           '-device', f'loader,file={out}/ram.bin,addr={img_start:#x},force-raw=on',
           '-device', f'loader,file={out}/stub.bin,addr={qt.STUB_PA:#x},force-raw=on',
           '-device', f'loader,addr={qt.STUB_PA:#x},cpu-num=0']
    p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(a.secs)
    q = qt.QMP(mon)
    q.call('stop')
    open(f'{out}/regs.txt', 'w').write(q.hmp('info registers'))
    q.hmp(f'pmemsave {qt.FB_BASE:#x} {out}/fb.raw {qt.FB_STRIDE * qt.FB_H}')
    if not os.path.exists(f'{out}/fb.raw'):
        q.call('pmemsave', val=qt.FB_BASE, size=qt.FB_STRIDE * qt.FB_H, filename=f'{out}/fb.raw')
    p.kill()
    p.wait()
    if os.path.exists(f'{out}/fb.raw'):
        qt.write_png(f'{out}/fb.png', open(f'{out}/fb.raw', 'rb').read())
        os.unlink(f'{out}/fb.raw')
    else:
        print('[*] framebuffer dump failed')
    print(f'[*] fb -> {out}/fb.png, serial -> {out}/serial.txt')
    ser = open(f'{out}/serial.txt', 'rb').read().decode('utf-8', 'replace')
    if ser.strip():
        print('=== serial tail ===')
        print('\n'.join(ser.splitlines()[-40:]))


if __name__ == '__main__':
    main()
