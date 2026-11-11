#!/usr/bin/env python3
"""Build the tulip diagnostic shim and pack fastboot-bootable images.

Usage: python3 build.py STOCK_BOOT_IMG DTB_DIR_WITH_FDT_PY [PAYLOAD]
Needs clang, ld.lld, llvm-objcopy, llvm-nm. Produces out/tulip-shim-24bpp.img and
out/tulip-shim-32bpp.img. The images are NOT flashed; use `fastboot boot`.
"""
import hashlib, os, shutil, struct, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
STOCK = sys.argv[1]
TOOLS = sys.argv[2]
sys.path.insert(0, TOOLS)
import fdt  # minimal DTB parser

SRCS = ["start.S", "shim.c", "console.c", "mmu.c", "fdt.c", "loader.c"]
CFLAGS = ["-target", "aarch64-none-elf", "-O2", "-ffreestanding", "-fno-builtin", "-nostdlib",
          "-fno-pic", "-mgeneral-regs-only", "-mstrict-align", "-fno-stack-protector",
          "-Wall", "-Wextra", "-I", HERE]


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        print(" ".join(cmd)); print(r.stdout); print(r.stderr); sys.exit(1)
    if r.stderr.strip():
        print(r.stderr)
    return r.stdout


def build_shim(bpp, ping=False, boot=False):
    d = os.path.join(OUT, f"b{bpp}" + ("p" if ping else "") + ("x" if boot else ""))
    os.makedirs(d, exist_ok=True)
    objs = []
    for s in SRCS:
        o = os.path.join(d, os.path.splitext(s)[0] + ".o")
        run(["clang"] + CFLAGS + [f"-DFB_BPP={bpp}"] + (["-DPING=1"] if ping else []) + (["-DBOOT_XNU=1"] if boot else []) + ["-c", os.path.join(HERE, s), "-o", o])
        objs.append(o)
    elf = os.path.join(d, "shim.elf")
    run(["ld.lld", "-T", os.path.join(HERE, "shim.ld"), "--build-id=none", "-N", "-o", elf] + objs)
    img = os.path.join(d, "Image")
    run(["llvm-objcopy", "-O", "binary", elf, img])
    end = None
    for line in run(["llvm-nm", elf]).splitlines():
        p = line.split()
        if len(p) == 3 and p[2] == "_end":
            end = int(p[0], 16)
    data = open(img, "rb").read()
    assert end and end >= len(data)
    data += b"\0" * (end - len(data))
    # the image header must advertise _end both as image_size and at 0x2c
    assert struct.unpack("<Q", data[16:24])[0] == end, "image_size != _end"
    assert struct.unpack("<I", data[0x2c:0x30])[0] == end, "LK dtb offset != _end"
    assert data[56:60] == b"ARM\x64"
    return data


def e7t_dtbs(stock):
    """All appended DTBs of the stock kernel that belong to this phone (E7T, SDM636)."""
    import zlib
    (ks, ka, rs, ra, ss, sa, ta, ps, hv, osv) = struct.unpack("<10I", stock[8:48])
    k = stock[ps:ps + ks]
    dec = zlib.decompressobj(31)
    dec.decompress(k)
    tail = dec.unused_data
    out, i = [], 0
    while i + 8 <= len(tail):
        if tail[i:i + 4] == b"\xd0\x0d\xfe\xed":
            sz = struct.unpack(">I", tail[i + 4:i + 8])[0]
            blob = tail[i:i + sz]
            root = fdt.parse(blob)["kids"][""]["props"]
            model = b"".join(fdt.strs(root.get("model", b"")) and [root["model"]]).decode("latin1")
            if "E7T" in model and fdt.u32s(root.get("qcom,msm-id", b""))[:1] == [345]:
                out.append(blob)
            i += sz
        else:
            i += 1
    return out


def pack_bootimg(stock, kernel, out_path, ramdisk_override=None):
    (ks, ka, rs, ra, ss, sa, ta, ps, hv, osv) = struct.unpack("<10I", stock[8:48])
    assert hv == 0
    pg = lambda n: (n + ps - 1) // ps * ps
    koff = ps
    stock_k = ks
    roff = koff + pg(stock_k)
    ramdisk = stock[roff:roff + rs] if ramdisk_override is None else ramdisk_override
    name = stock[48:64]
    cmdline = stock[64:576]
    extra = stock[608:1632]
    h = hashlib.sha1()
    for blob in (kernel, ramdisk, b""):
        h.update(blob)
        h.update(struct.pack("<I", len(blob)))
    ident = h.digest() + b"\0" * 12
    hdr = b"ANDROID!" + struct.pack("<10I", len(kernel), ka, len(ramdisk), ra, 0, sa, ta, ps, 0, osv)
    hdr += name + cmdline + ident + extra
    hdr = hdr.ljust(ps, b"\0")
    body = kernel.ljust(pg(len(kernel)), b"\0") + ramdisk.ljust(pg(len(ramdisk)), b"\0")
    open(out_path, "wb").write(hdr + body)
    return hashlib.sha256(hdr + body).hexdigest()


def main():
    import gzip
    payload = open(sys.argv[3], 'rb').read() if len(sys.argv) > 3 else None
    os.makedirs(OUT, exist_ok=True)
    stock = open(STOCK, "rb").read()
    dtbs = b"".join(e7t_dtbs(stock))
    assert dtbs, "no E7T DTB found"
    for bpp in (24, 32):
        shim = build_shim(bpp)
        p = os.path.join(OUT, f"tulip-shim-{bpp}bpp-gz.img")
        print("[+]", p, pack_bootimg(stock, gzip.compress(shim, 9, mtime=0) + dtbs, p)[:16])
    if payload is not None:
        boot = build_shim(32, boot=True)
        open(os.path.join(OUT, "tulip-shim-boot.bin"), "wb").write(boot)
        p = os.path.join(OUT, "tulip-boot.img")
        print("[+]", p, pack_bootimg(stock, gzip.compress(boot, 9, mtime=0) + dtbs, p, payload)[:16], "payload", len(payload))
    # liveness-test variants: differ only in how the bootloader is asked to load them
    ping = build_shim(24, ping=True)
    a = ping
    b = bytearray(ping); b[8:16] = struct.pack("<Q", 0x80000); b = bytes(b)
    gz = gzip.compress(ping, 9, mtime=0)
    for name, kern in (("A-raw", a + dtbs), ("B-raw-textoff", b + dtbs), ("C-gzip", gz + dtbs)):
        p = os.path.join(OUT, f"tulip-ping-{name}.img")
        print("[+]", p, pack_bootimg(stock, kern, p)[:16])


if __name__ == "__main__":
    main()
