#!/usr/bin/env python3
"""Pack the tulip boot shim + XNU payload into a fastboot-bootable Android boot image.

Usage: python3 -I pack_boot.py STOCK_BOOT_IMG SHIM_BIN PAYLOAD OUT_IMG

STOCK_BOOT_IMG is your own dump of the phone's boot partition (never uploaded anywhere).
Its header fields, cmdline and ramdisk are reused; the kernel becomes gzip(shim) + the E7T DTB,
and the ramdisk slot carries the XNU payload. Test with `fastboot boot OUT_IMG`; nothing is flashed.
"""
import gzip, hashlib, os, struct, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools"))
import fdt


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
    stock = open(sys.argv[1], "rb").read()
    shim = open(sys.argv[2], "rb").read()
    payload = open(sys.argv[3], "rb").read()
    dtbs = b"".join(e7t_dtbs(stock))
    assert dtbs, "no E7T DTB in the stock boot image (is this the tulip boot.img?)"
    print("[+]", sys.argv[4], pack_bootimg(stock, gzip.compress(shim, 9, mtime=0) + dtbs, sys.argv[4], payload)[:16], "payload", len(payload))


if __name__ == "__main__":
    main()
