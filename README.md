# ios-tulip

**Apple's XNU kernel on the Xiaomi Redmi Note 6 Pro (tulip, Qualcomm SDM636)**

A research bring-up of Apple's open-source Darwin kernel on a Snapdragon 636 phone.
The boot chain, the device tree, the kernel patches and the early drivers are ours;
the kernel is Apple's, built from source.

xnu-8796 (iOS 16 generation) · ARMv8.0-A · 4K pages · GICv3 · eMMC 5.1

---

## Status

**2026-11-12** — The kernel boots on the phone AND in QEMU up to IOKit:
arm_init → arm_vm_init → pmap_bootstrap → zone_init → VM bootstrap → OSLog,
with IOKit registry lookups running and no panic. The next wall is the root
device: the eMMC driver is in, root mount is not yet reached.

| Area | State | Notes |
|---|---|---|
| Kernel build (CI, macOS) | OK | xnu-8796, MACHINE_CONFIG=VINCE, -march=armv8-a -mcpu=cortex-a53 |
| Boot chain (shim → XNU) | OK | gzip'd shim in the boot.img kernel field, raw payload in ramdisk |
| Apple Device Tree (ADT) | OK | generated per device, validator checks pass |
| Early console | OK | framebuffer text + stage bands (VINCE EARLY 1..13) |
| GICv3 | OK | 0x17a00000, redistributors 0x17b00000, vtimer PPI 19 |
| pmap / VM bootstrap | OK | 61 maps, 112 entries, 117 holes left |
| zone allocator | OK | pgzalloc, 357 slots |
| IOKit registry | OK | driver matching runs |
| eMMC 5.1 (SDHCI v5) | WAIT | polled ADMA2 driver added; on-device test pending |
| Root filesystem | TODO | HFS+ root on userdata, rd=emmcroot0 |
| launchd / userland | TODO | needs root |
| Display (SpringBoard) | TODO | IOMobileFramebuffer / AppleCLCD |
| Touch | TODO | FocalTech FTS over I2C |
| Wi-Fi / BT / audio / camera / GPU | NO | not started |

---

## Hardware (tulip / SDM636)

Everything below was read from the live device (stock DTB, /proc/iomem, LK splash),
not guessed.

| Block | Value |
|---|---|
| SoC | Qualcomm SDM636 — 4x Cortex-A53 + 4x Cortex-A73, ARMv8.0-A, no LSE atomics |
| RAM | contiguous bank from 0xa0400000; kernel budget 0x5c000000 (1.44 GiB) |
| GIC | GICv3 distributor 0x17a00000 (64 KiB), redistributors 0x17b00000 (1 MiB) |
| Generic timer | PPI 19, 19.2 MHz XO |
| Display | continuous splash framebuffer 0x9d400000, 1080x2280, 32 bpp, stride 4320 |
| Storage | eMMC 5.1, Qualcomm SDHC v5 at 0x0c0c4000 |
| Touch | FocalTech FTS, I2C address 0x38, bus at 0x0c175000 |
| Identity presented to iOS | iPhone X (iPhone10,3 / D22AP) |

---

## Boot chain

    Android fastboot  (stock ABL, unlocked bootloader)
      fastboot flash boot boot.img
           kernel  : shim, gzip-compressed   (the bootloader refuses raw kernels)
           ramdisk : payload, raw            (the shim parses the magic itself)
           dtb     : stock tulip DTB         (LK appends /chosen initrd ranges)
         |
         v
         shim (bare metal, no UEFI)
           - sets up bootstrap page tables, maps the kernel + a low 1 GiB device window
           - reads the live FDT, finds initrd start/end
           - copies every Mach-O segment to its physical address
           - writes boot_args (physBase, virtBase, topOfKernelData, framebuffer, DT ptr)
           - flushes caches, MMU off, jumps to the kernel entry
             |
             v
           XNU
             arm_init -> PE_init_platform -> CPU topology -> cpu_bootstrap
             arm_vm_init -> arm_vm_prot_init -> TTBR0 off -> physmap -> pmap_bootstrap
             bsd_init -> setconf -> vfs_mountroot -> launchd

Two details that cost days and are now encoded in the tree:

- **deviceTreeP must be a physical address.** boot_args is consumed while the
  bootstrap translation is still 1:1; a virtual address reads as zeros and the
  kernel reports "Expected 64 seed bytes from bootloader, but got 0". Once TTBR0
  is gone the DT is re-pointed through the physmap (patch 0191).
- **debug=0xc must not be set on this port.** It routes panics into a debugger
  stub containing a word the A53 cannot execute, which replaces the panic text
  with silence.

---

## Repository layout

    shim-tulip/            bare-metal loader (C + AArch64 asm); built into boot.img
    tools/
      mkadt_tulip.py       Apple Device Tree generator for tulip
      verify_adt_tulip.py  sanity checks (RAM, GIC, framebuffer, CPU nodes)
      mkpayload_tulip.py   Mach-O + ADT + boot-args -> payload (chained fixups)
      mkbootimg_vince.py   Android boot.img v0 packer
    xnu/
      patches/             ordered patch series, applied by CI over Apple's xnu-8796
      files/               new source files added by the series
    qemu-tulip-run.py      QEMU harness: GICv3, tulip framebuffer, PC sampling, RAM dump
    dumplog.py             extract the kernel console log out of a RAM dump
    fastsample.py          100 ms PC sampling — tells "spinning" from "working"
    stackwalk.py           walk the kernel stack for the current call chain
    flash.sh / go.sh       1-second flash via the Windows fastboot binary

---

## Quick start

### 1. Kernel (GitHub Actions, macOS)

    gh workflow run xnu-tulip.yml
    gh run download <RUN_ID> -n xnu-kernel-tulip -D /tmp/kout
    cp /tmp/kout/kernel.development.vince kernel/

### 2. ADT, payload, boot image

    python3 -I tools/mkadt_tulip.py out/tulip.adt
    python3 -I tools/verify_adt_tulip.py out/tulip.adt

    python3 -I tools/mkpayload_tulip.py kernel/kernel.development.vince \
        out/tulip.adt out/tulip.payload --trustcache tc.bin \
        --cmdline "serial=3 cpus=1 keepsyms=1 -noprogress wdt=-1 emmcroot=userdata"

    python3 shim-tulip/build.py stock-boot.img shim-tulip/tools out/tulip.payload

### 3. Flash

    fastboot flash boot shim-tulip/out/tulip-boot.img
    fastboot reboot

The shim goes into the kernel field gzip-compressed: this bootloader rejects raw
kernel images, and the shim (not the bootloader) decompresses the payload — so the
ramdisk field must stay raw.

---

## Boot arguments that matter

| Argument | Effect |
|---|---|
| cpus=1 | boot on one core; SMP comes later |
| keepsyms=1 | keep symbols for panic backtraces |
| wdt=-1 | disable hardware watchdogs during bring-up |
| -noprogress | no boot progress UI |
| emmcroot=userdata | GPT partition exposed as emmcroot0 (default userdata) |
| rd=emmcroot0 | use that volume as root |
| emmcrw=1 | allow writes (off by default; writes stay inside the partition) |
| serial=3 | configure the serial-debug console path |
| debug=0xc | DO NOT SET — see above |

---

## Debugging

Replacing "film the phone screen" with tooling was the single biggest speed-up in
this project.

    python3 qemu-tulip-run.py out/tulip-qemu.payload qemu-out 60 15
    python3 dumplog.py qemu-out/ramdump.bin                # kernel console text
    python3 fastsample.py out/tulip-qemu.payload q 4 0.1   # which function is hot
    python3 stackwalk.py out/tulip-qemu.payload q 40       # call chain

qemu-tulip-run.py samples PC and symbolises it against the kernel:

    t= 15s _ml_get_timebase+0x1c
    t= 30s __doprnt+0x8b0        <- printf works; what is missing is the console

---

## Patch series philosophy

The tree is a mix of three existing ports plus one for storage, chosen by what each
one got right rather than by device:

| Source | What we took | What we did not |
|---|---|---|
| dipa-studio/ios-sweet | kernel core: pmap, IOKit, HFS+, AMFI, sandbox, IOSurface, HID | UFS storage, Goodix SPI touch, Adreno |
| vince port (MSM8953) | boot chain, ADT/payload tooling, 4K-page + A53 MMU fixes, eMMC skeleton | GICv2, MSM8953 addresses |
| parukovvadim/ios-whyred, N1709/ios-whyred2 | eMMC SDHCI v5 (ADMA2), whyred/lavender GCC clock layout | UFS, Synaptics touch |
| HakiOS | virtio-blk for QEMU root, the logdump idea | UFS (70 KB), SC7280 drivers |

Rule of thumb: sweet gives the kernel, vince the loader, whyred the storage,
tulip the numbers.

---

## Credits & licensing

- **Apple Inc.** — XNU and the open-source libraries, under APSL 2.0.
- **dipa-studio/ios-sweet** — the original Snapdragon XNU bring-up this port descends from.
- Files marked "Adapted from ..." keep their origin in the header and remain under
  the license of the file they patch (APSL 2.0 for XNU sources).

No Apple userland is distributed here; an iOS root filesystem is built locally from
an IPSW you supply yourself.

---

## Roadmap

1. eMMC on hardware: partition enumeration, HFS+ read
2. HFS+ root from userdata -> vfs_mountroot
3. launchd and the daemon set
4. IOMobileFramebuffer / AppleCLCD presentation
5. FocalTech FTS touch -> HID events
6. SMP: start the A73 cluster via PSCI
7. Persistent console log on the system partition

