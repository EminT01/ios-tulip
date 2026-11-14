# ios-tulip - Bring-up status

Experimental Apple XNU (xnu-8796.141.3) boot port for the **Xiaomi Redmi Note 6 Pro (tulip)**,
Qualcomm **SDM636**. This repository holds only the patch series applied to a stock xnu tree
(`patches/`); the kernel itself is built in CI.

---

## Where we are

The kernel boots on the device with no panic:

```
zone_init -> VM bootstrap done -> OSLog configured -> APFS/HFS+ registered
  -> bsd_init -> machine_lockdown -> ml_wait_max_cpus -> ifnet_attach (lo0/gif0/stf0)
  -> TULIP SDHCI probe   <-- stuck here
```

Only the eMMC block device stands between us and `IOFindBSDRoot`.

---

## Milestones cleared

| Area | Patch | Result |
|---|---|---|
| GIC bootstrap (1 GiB low device L1 block) | 0090 | GICR fault fixed |
| `assert(segSizeTEXT)` in `arm_vm_prot_init` | 0190 | diagnostics, then fixed |
| Device tree moved into the physmap | 0191 | DT readable from kern |
| `debug=0xc` boot-arg | - | removed (caused `DebuggerTrapWithState`) |
| CPU shootdown deadlock (`ml_set_max_cpus`) | 0198, 0210 | `bsd_init` reached |
| SDCC v5 register layout (`MCI_VERSION` at +0x318) | 0212 | `0x1000086b`, `HOST_VERSION 0x6b02` |
| HFS+ read-only registration | - | `hfs: 627.100.6 registered` |

---

## Current blocker: the SDHCI card-clock gate hangs the AXI bus

**Symptom.** The display freezes right after:

```
TULIP SDHCI: probe step 0: VENDOR_SPEC 0x02128480 (MCLK sel 2, PWRSAVE 1)
TULIP SDHCI: probe step 0: DLL_CONFIG 0x0705604c: DLL_STATUS 0x0000001c
```

No panic, no watchdog, no further output. The CPU is not spinning in a `delay()` loop;
it is stalled on a bus access.

**Root cause.** `sdhci_enable_card_clock()` starts with:

```c
hc_wr16(SDHCI_CLOCK_CONTROL, 0);          /* gate the card clock off */
hc_wr16(SDHCI_CLOCK_CONTROL, SDHCI_CLOCK_INT_EN);
clk = hc_rd16(SDHCI_CLOCK_CONTROL);       /* <- never returns */
```

Clearing the gate drops MCLK on the v5 core. The AXI slave stops answering and the
following read never completes, so even the 150 ms `INT_STABLE` timeout never runs.
Same failure that produced the missing "after" line back in 0211.

Confirmed by elimination: `probe step 2: gate card clock, UHS=0, GCC 400 kHz` and
`probe step 2: CLOCK_CONTROL ...` are never printed, so the hang sits in step 5 of
`sdhci_take_over()`, before any GCC write.

**Side findings.**
- `CORE_DLL_LOCK` was `BIT(7)`; Qualcomm defines `DLL_LOCK` at `BIT(0)` and
  `DLL_READY` at `BIT(2)`. The observed `DLL_STATUS 0x1c` decoded as "no lock"
  instead of "ready, no lock".
- `sdhci_gcc_set_apps()` documents an NOC FSM guard in comments and defines
  `GCC_BRANCH_NOC_ON/MASK`, but never checked them before writing RCGR. Writing
  while the branch is not on the NOC locks the AXI bus - a second, latent hang.

---

## What 0214 does

1. **Read-before-write** in `sdhci_enable_card_clock()`: if `CARD_EN` and `INT_STABLE`
   are already set, return 0 without touching the register. Otherwise log the current
   value and `CORE_VENDOR_SPEC` first.
2. **`CORE_DLL_LOCK` -> `BIT(0)`**, add `CORE_DLL_READY` (`BIT(2)`).
3. **NOC halt guard** in `sdhci_gcc_set_apps()`: return `EIO` before any `gcc_wr()` if
   `(cbcr & GCC_BRANCH_NOC_MASK) != GCC_BRANCH_NOC_ON`.
4. **`noclkgate=1`** boot-arg skips step 5 entirely and trusts LK card clock.

Expected next boot: no hang, and `CMD13` / `CMD0` / `CMD1` / `OCR` / `GPT` lines.

---

## Next steps

1. Boot with `noclkgate=1`, confirm the probe reaches CMD13/CMD0/CMD1.
2. CMD1 OCR bit31 -> ALL_SEND_CID -> CMD3 RCA -> EXT_CSD read.
3. Parse the GPT, find `userdata`, mount HFS+ read-write.
4. `IOFindBSDRoot` returns a real device -> `launchd`.
5. After launchd: backboardd / SpringBoard, sandbox + AMFI disable, IOSurface +
   IOMobileFramebuffer presentation.

---

## Reference trees

| Tree | SoC | Use |
|---|---|---|
| `work/bt/whyred2`, `parukovvadim/ios-whyred` | SDM636 (same SoC) | eMMC v5.1 init, GCC clocks, LSE atomics, PSCI to Gold |
| `dipa-studio/ios-sweet` | SM7150 | `VINCE` board config basis, IOKit skeleton, FB console |
| `MakrSas/ios-topaz` | SM6225 | methodology for root mount, launchd, SpringBoard |
| `oosexgang/hakios-xnu-kernel` | - | GPU / Adreno / Mesa side |

## Build and flash

CI builds on push to `main`; patches live in `patches/` and are applied in order.
Validate every patch against the local tree before pushing:

```bash
cd ~/work/tulipchain
patch -p1 --forward --dry-run < <patch>
```

Flash loop: `mkpayload_tulip.py` + `shim-tulip/build.py`, then `fastboot boot`.
