# ios-tulip

Experimental Apple XNU (xnu-8796.141.3) boot port for the **Redmi Note 6 Pro
(tulip)**, Qualcomm **SDM636**. This repo holds only the patch series applied to
a stock xnu tree; the kernel is built in CI.

## Where we are

The kernel boots with **no panic, and the internal eMMC is fully working**.
Probe completes, the card is identified, sectors are read over PIO, the partition
table parses, and the driver publishes `emmcroot0` as a real block device.
`IOFindBSDRoot` now returns a device instead of failing with `ENXIO`.

    zone_init -> VM bootstrap -> OSLog configured -> APFS/HFS+ registered
      -> bsd_init -> machine_lockdown -> ml_wait_max_cpus -> ifnet_attach
      -> TULIP SDHCI probe .... returned 0 (emmcroot0, major 1, minor 0)
      -> root mount of "userdata" -> HFS+ signature mismatch (expected)

The only thing left before `launchd` is a filesystem that actually contains an
Apple system root.

## What the eMMC bring-up proved

`emmcprobe=1 sdcclk=1 noreset=1 cpus=1`:

    MCI_VERSION 0x1000086b / HOST_VERSION 0x6b02   SDCC v5 confirmed
    CMD9 SEND_CSD  -> CSD 0x06278132, 29820 MiB, 8-bit
    CMD7 SELECT_CARD -> RCA 2, state 4 (TRAN)
    CMD13          -> R1 0x00000900
    CMD8 SEND_EXT_CSD -> 512-byte read at 400 kHz
    self-test      -> b0..b5 == 55 aa (MBR signature), PIO works
    CMD6 HS_TIMING=1, CMD6 BUS_WIDTH=8 -> R1 0x00000900
    enumeration complete: 25 MHz, 8-bit, high-speed
    "system"   0x220000, 3072 MiB
    "userdata" 0xdc0000, 22779 MiB (read-only)
    probe returned 0: emmcroot0, major 1, minor 0

Root mount then fails cleanly, exactly as intended for an Android data
partition: `unknown Volume Signature : 4503`, `hfs_mountfs returned error=22`,
`cannot mount root, error = 19`. That is `EINVAL` on the volume header and
`ENODEV` on the root - **not** a panic. The mount path works and rejects a
non-HFS+ volume properly.

## The three real bugs behind every earlier freeze

**1. Wrong SDCC register layout.** SDM636 has an SDCC v5 core: the native SDHCI
window sits at the start of the block and the vendor registers live at
0x2xx/0x3xx, with `MCI_VERSION` at +0x318. The driver used the msm8937 layout
(`MCI_VERSION` at +0x50), which reads zero on v5. Patch 0212 selects the v5
layout for tulip.

**2. `delay()` parked the bootstrap thread forever.** `ml_delay_should_spin()`
returns FALSE while `cpu_idle_latency` is still 0 during early boot, so
`delay()` falls through to `assert_wait_deadline()` + `thread_block()`. The
bootstrap thread blocks and no timer wakeup ever reaches it. Every wait in the
driver looked like an AXI hang - the log simply stopped. Patch 0217 spins on
`mach_absolute_time()` instead.

**3. The card clock was never programmed.** LK leaves SDCC1 near 192 MHz, which
is not a legal identification clock: CMD1 returned in ~4 us with junk OCR. With
`sdcclk=1` the GCC RCG (XO 19.2 MHz / 48) puts `sdcc1_apps` at 400 kHz,
responses take hundreds of microseconds, and OCR reads `0xc0ff8080`.

A fourth, latent trap was closed on the way: `sdhci_gcc_set_apps()` defined the
NOC FSM guard but never checked it before writing RCGR. A write while the branch
is off the NOC locks the AXI bus. 0214 bails out with `EIO` instead.

## Patch timeline

| Patch | What it fixed |
|---|---|
| 0090 | GIC bootstrap: 1 GiB low device L1 block |
| 0190 | `assert(segSizeTEXT)` in `arm_vm_prot_init` |
| 0191 | Device tree moved into the physmap |
| 0198, 0210 | CPU shootdown deadlock (`ml_set_max_cpus`) |
| 0212 | SDCC v5 register layout -> `MCI_VERSION 0x1000086b` |
| 0214 | Card-clock gate never blind-written; `DLL_LOCK` is BIT(0); NOC guard |
| 0215 | `noreset=1` skips `RESET_ALL` (never self-clears here) |
| 0216 | Trace around the 1 ms delay and CMD13 |
| 0217 | Spin instead of `delay()` |

## Boot args

    emmcprobe=1    probe and enumerate the eMMC without mounting anything
    sdcclk=1       program sdcc1_apps_clk_src to 400 kHz through GCC
    noreset=1      skip SDHCI RESET_ALL (it never self-clears on this core)
    noclkgate=1    skip the card-clock gate rebuild, trust LK's clock
    emmcroot=<p>   partition to publish as root device (userdata, system)
    rd=emmcroot0   mount the published root read-only
    cpus=1         single CPU (TULIP_SMP off)

## Next: getting an Apple root onto the device

Two paths, both needing an explicit go-ahead first.

**Ramdisk (`rd=md0`)** - disk untouched, 3-4 patches. Needs the `md(4)` driver
ported back into this tree (`bsd/dev/md.c` is absent from `bsd/conf/files`), a
`setconf()` branch calling `bsd_rooted_ramdisk()` (it exists but is only used at
bsd_init.c:926, never to choose the root device), and code that consumes the ADT
`/chosen/memory-map/Ramdisk` node that `mkpayload_tulip.py --ramdisk` already
writes.

**eMMC partition** - destructive: reformat `userdata` (22.7 GiB) as HFS+ and
place a root there. `system` (3 GiB) is too small for iOS 16. Back up first.

Then: `IOFindBSDRoot` -> `/sbin/launchd` -> backboardd / SpringBoard ->
sandbox + AMFI disable -> IOSurface + IOMobileFramebuffer presentation.

> Nothing has been written to the device. Every test so far is read-only.

## Reference trees

| Tree | SoC | Use |
|---|---|---|
| `work/bt/whyred2`, `parukovvadim/ios-whyred` | SDM636 (same SoC) | eMMC v5.1 init, GCC clocks, LSE atomics, PSCI to Gold |
| `dipa-studio/ios-sweet` | SM7150 | `VINCE` board config basis, IOKit skeleton, FB console |
| `MakrSas/ios-topaz` | SM6225 | methodology for root mount, launchd, SpringBoard |
| `oosexgang/hakios-xnu-kernel` | - | GPU / Adreno / Mesa side |

## Build and flash

CI builds on push to `main`; patches in `patches/` are applied in order.
Validate before pushing:

    cd ~/work/tulipchain && patch -p1 --forward --dry-run < <patch>

Flash: `mkpayload_tulip.py` + `shim-tulip/build.py`, then `fastboot boot`
(or `./flash.sh` for the boot partition).
