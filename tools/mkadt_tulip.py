#!/usr/bin/env python3
"""Build the Apple Device Tree (ADT) for Xiaomi Redmi Note 6 Pro (tulip) Qualcomm SDM636.

Derived from mkadt_vince.py. Every value below was measured on the phone (recovery /proc/iomem, dmesg, stock DTB #29):
- GICv3: GICD 0x17a00000 (64 KiB), GICR 0x17b00000 (1 MiB, 8 x 128 KiB), virtual-timer-intid 19
- Framebuffer @ 0x9d400000, 1080x2280, 32-bpp, stride 4320 (36 MiB reserved by LK)
- Usable RAM: one contiguous bank 0xa0400000.. (0xa0000000 is the 4 MiB ramoops region)
- eMMC: Qualcomm SDHCI v5, hc 0x0c0c4000, core 0x0c0c5000
- FocalTech FTS touchscreen 0x38 on the i2c at 0x0c175000 (reset GPIO 66, irq GPIO 67)
- iPhone X identity for iOS userland (display-scale 3, no-home-button)
- First milestone: ONE cpu (cpu0, MPIDR 0, Kryo 260 Silver). SMP later.
"""
import hashlib
import os
import struct
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adt  # noqa: E402

# Vince (MSM8953) Hardware Definitions:
# DRAM Base: 0xa0000000 (verified by live /proc/iomem: 0xa0000000-0xffffffff is 1.5 GB contiguous)
PHYS_BASE = 0xa0400000
MEM_SIZE = 0x5c000000  # 1.44 GiB: 0xa0400000..0xfc3fffff, inside the RAM bank that ends at 0xfeabffff

PANIC_LOG_SIZE = 0x100000  # 1 MB panic log buffer

# Non-zero SOC base for arm-io so pe_arm_get_soc_base_phys() returns non-zero
SOC_BASE = 0x01000000
# (GIC reg values in the ADT are offsets from SOC_BASE: pe_fiq.c adds pe_arm_get_soc_base_phys())

# GICv2 (Qualcomm QGIC2) MMIO addresses
GICD, GICD_SIZE = 0x17a00000, 0x10000
GICR, GICR_SIZE = 0x17b00000, 0x100000

# Framebuffer: Continuous splash left by LK (24-bit RGB888, stride 3240)
FB, FB_SIZE = 0x9d400000, 1080 * 2280 * 4
FB_W, FB_H, FB_STRIDE = 1080, 2280, 1080 * 4
FB_TOP = 96  # pixel rows hidden by the notch / status area are left out of the console

# Storage: Qualcomm SDHCI eMMC 5.1 host controller
SDHCI, SDHCI_SIZE = 0x0c0c4000, 0x1000
SDHCI_CORE = 0x0c0c5000

TIMEBASE = 19200000  # 19.2 MHz Qualcomm XO clock
VTIMER_INTID = 19    # CNTV: Qualcomm numbers the timer PPIs 1/2/3/0 (secure phys, phys, virt, hyp): 16 + 3

VINCE_ECID = 0x54554c4950000001  # 'TULIP' + 1
BOOT_MANIFEST_HASH = hashlib.sha384(b'tulip boot manifest').digest()

D22AP_ADT = os.environ.get('D22AP_ADT', os.path.join(os.path.dirname(os.path.abspath(__file__)), '../research/ipsw-x/d22ap.adt'))

def d22ap_product(path=D22AP_ADT):
    """Fallback or extract /product properties from iPhone X device tree."""
    if os.path.exists(path):
        root, _ = adt.parse(open(path, 'rb').read())
        for c in root.children:
            if dict((k, v) for k, f, v in c.props).get('name') == b'product\0':
                return [(k, v) for k, f, v in c.props if not f and k not in ('name', 'AAPL,phandle')]
    return None

u32 = lambda *v: struct.pack('<%dI' % len(v), *v)
u64 = lambda *v: struct.pack('<%dQ' % len(v), *v)
cstr = lambda s: s.encode() + b'\0'

def node(name, props=(), children=()):
    n = adt.Node()
    n.props = [('name', 0, cstr(name))] + [(k, 0, v) for k, v in props]
    n.children = list(children)
    return n

def build_tulip_adt(seed=None):
    phys_base = PHYS_BASE
    mem_size = MEM_SIZE

    panic_base = phys_base + mem_size - PANIC_LOG_SIZE
    mem_size -= PANIC_LOG_SIZE

    seed = seed if seed is not None else os.urandom(64)
    phandle = iter(range(1, 1000))
    ph = lambda: ('AAPL,phandle', u32(next(phandle)))

    chosen = node('chosen', [
        ph(),
        ('dram-base', u64(phys_base)),
        ('dram-size', u64(mem_size)),
        ('random-seed', seed),
        ('debug-enabled', u32(1)),
        ('display-scale', u32(3)),
        ('display-rotation', u32(0)),
        ('unique-chip-id', u64(VINCE_ECID)),
        ('chip-id', u32(0x8015)),  # Apple A11 Bionic (iPhone X)
        ('board-id', u32(0x16)),
        ('embedded-panic-log-size', u32(PANIC_LOG_SIZE)),
        ('firmware-version', cstr('vince-shim')),
        ('system-firmware-version', cstr('vince-shim')),
        ('boot-manifest-hash', BOOT_MANIFEST_HASH),
        ('crypto-hash-method', cstr('sha2-384')),
        ('certificate-production-status', u32(0)),
        ('effective-production-status-ap', u32(0)),
        ('certificate-security-mode', u32(1)),
        ('effective-security-mode-sep', u32(1)),
    ], [
        node('memory-map', [ph()]),
        node('asmb', [ph(), ('lp-sip0', u64(0x6f)), ('lp-sip1', u32(1))])
    ])

    # GICv3 node: pe_fiq.c (HAS_GIC_V3) looks up /arm-io/gic and reads reg = <GICD GICD_SIZE GICR GICR_SIZE>
    # as offsets from the arm-io SoC base, plus virtual-timer-intid.
    gic = node('gic', [
        ph(),
        ('compatible', cstr('arm,gic-v3') + b'\0'),
        ('reg', u64(GICD - SOC_BASE, GICD_SIZE, GICR - SOC_BASE, GICR_SIZE)),
        ('interrupt-controller', b''),
        ('#interrupt-cells', u32(3)),
        ('virtual-timer-intid', u32(VTIMER_INTID)),
    ])

    # Watchdog node with no-pmu flag to prevent watchdogd panic
    wdt = node('wdt', [
        ph(),
        ('no-pmu', u32(1)),
    ])

    # Display subsystem node for backboardd / IOMobileFramebuffer
    disp0 = node('disp0', [
        ph(),
        ('device_type', cstr('display-subsystem')),
        ('compatible', cstr('tulip,display') + cstr('vince,display') + cstr('sweet,display') + b'\0'),
        # IOMobileFramebuffer reads the canvas from this node: the iPhone X size AppleCLCD presents (1125x2436,
        # 375x812 points @3x; the panel shows the centered 1080x2160 part), as sweet's ADT does.
        ('canvas-width', u32(1125)),
        ('canvas-height', u32(2436)),
    ])

    # SDHCI eMMC Storage Node
    sdhci_node = node('sweet-ufs', [
        ph(),
        ('compatible', cstr('generic-sdhci') + cstr('qcom,sdhci-msm-v5') + b'\0'),
        ('reg', u64(SDHCI, SDHCI_SIZE, SDHCI_CORE, 0x1000)),
        ('interrupts', u32(0, 125, 4)),
    ])

    # Synaptics RMI4 Touchscreen Node
    touch_node = node('touchscreen', [
        ph(),
        ('compatible', cstr('focaltech,fts') + b'\0'),
        ('i2c-address', u32(0x38)),
        ('i2c-base', u64(0x0c175000)),
        ('reset-gpio', u32(66)),
        ('irq-gpio', u32(67)),
    ])

    # No Wi-Fi or Bluetooth driver: MobileGestalt's WifiAddress/BluetoothAddress (for the A11-style UniqueDeviceID)
    # look up IONameMatch wlan / bluetooth and read local-mac-address; with no such service it waits for an
    # IONetworkController, times out and retries forever (lsd's database seed hangs in GenerateBuiltInAppInstallSessionID,
    # SpringBoard and backboardd wait on lsd). Stub nubs with synthetic locally administered addresses, not the phone's.
    wlan = node('wlan', [
        ph(),
        ('device_type', cstr('wlan')),
        ('compatible', cstr('vince,wlan-stub')),
        ('local-mac-address', bytes([0x02, 0x56, 0x49, 0x4e, 0x43, 0x01])),
    ])
    bluetooth = node('bluetooth', [
        ph(),
        ('device_type', cstr('bluetooth')),
        ('compatible', cstr('vince,bluetooth-stub')),
        ('local-mac-address', bytes([0x02, 0x56, 0x49, 0x4e, 0x43, 0x02])),
    ])

    # arm-io with device_type and ranges so pe_arm_get_soc_base_phys() succeeds
    arm_io = node('arm-io', [
        ph(),
        ('device_type', cstr('vince-io')),
        ('compatible', cstr('vince-io') + cstr('arm-io') + b'\0'),
        ('#address-cells', u32(2)),
        ('#size-cells', u32(2)),
        ('ranges', u64(0, SOC_BASE, 0x100000000 - SOC_BASE)),
    ], [gic, wdt, disp0, sdhci_node, touch_node, wlan, bluetooth])

    # Vince Framebuffer console node for early kprintf
    fbcon = node('vince-fbcon', [
        ph(),
        ('reg', u64(FB + FB_TOP * FB_STRIDE, FB_SIZE - FB_TOP * FB_STRIDE)),
        ('width', u32(FB_W)),
        ('height', u32(FB_H - FB_TOP)),
        ('stride', u32(FB_STRIDE)),
        ('bpp', u32(32)),
    ])

    # System defaults
    defaults = node('defaults', [
        ph(),
        ('no-effaceable-storage', u32(1)),
    ])

    # Buttons: Home button type 2 = iPhone X style (gestures, no physical home button)
    buttons = node('buttons', [
        ph(),
        ('button-names', cstr('volup') + cstr('voldown') + cstr('hold')),
        ('home-button-type', u32(2)),
        ('opposed-power-vol-buttons', u32(1)),
    ])

    # CPUs: first milestone is single-CPU. cpu0 = Kryo 260 Silver (A53 class, MPIDR 0). The other seven
    # (Silver 1-3, Gold 4-7 at MPIDR 0x100..0x103) are added once PSCI/GICv3 SMP is brought up.
    cpu_nodes = []
    for core in (0,):
        c = node(f'cpu{core}', [
            ph(),
            ('device_type', cstr('cpu')),
            ('compatible', cstr('qcom,kryo260') + cstr('ARM,v8') + b'\0'),
            ('reg', u32(core)),
            ('cpu-id', u32(core)),
            ('cluster-id', u32(0)),
            ('cluster-type', u32(0)),
            ('die-cluster-id', u32(0)),
            ('cluster-core-id', u32(core)),
            ('state', cstr('running')),
            ('timebase-frequency', u32(TIMEBASE)),
            ('clock-frequency', u32(1800000000)),
            ('bus-frequency', u32(100000000)),
            ('memory-frequency', u32(1866000000)),
            ('peripheral-frequency', u32(TIMEBASE)),
            ('fixed-frequency', u32(TIMEBASE)),
            ('cpu-model', cstr('kryo260-silver')),
        ])
        cpu_nodes.append(c)

    cpus = node('cpus', [ph(), ('#address-cells', u32(1)), ('#size-cells', u32(0))], cpu_nodes)

    # Product identity: iPhone X (iPhone10,3 / D22AP)
    product_props = d22ap_product()
    if product_props:
        product = [node('product', [ph()] + product_props)]
    else:
        product = [node('product', [
            ph(),
            ('product-id', u32(0x1003)),
            ('product-name', cstr('iPhone X')),
            ('model-number', cstr('D22AP')),
            ('device-class', cstr('iPhone')),
        ])]

    # Panic log region: /pram reg = <panic_base, PANIC_LOG_SIZE>
    pram = node('pram', [ph(), ('reg', u64(panic_base, PANIC_LOG_SIZE))])

    root = node('device-tree', [
        ph(),
        ('compatible', cstr('D22AP') + cstr('iPhone10,3') + cstr('xiaomi,tulip') + cstr('xiaomi,vince') + cstr('qcom,sdm636') + cstr('AppleARM') + b'\0'),
        ('model', cstr('iPhone10,3')),
        ('target-type', cstr('vince')),   # IOKit/XNU patches key on the VINCE machine family
        ('target-sub-type', cstr('tulip')),
        ('manufacturer', cstr('Apple Inc.')),
        ('device-id', u64(VINCE_ECID)),
        ('timebase-frequency', u32(TIMEBASE)),
        ('#address-cells', u32(2)),
        ('#size-cells', u32(2)),
    ], [chosen, defaults, cpus, arm_io, fbcon, buttons, pram] + product)

    return root

def main():
    parser = argparse.ArgumentParser(description="Generate Tulip Apple Device Tree")
    parser.add_argument("output", help="Output .adt file path")
    parser.add_argument("--dump", action="store_true", help="Print human readable tree")
    args = parser.parse_args()

    root = build_tulip_adt()
    data = adt.serialize(root)
    with open(args.output, "wb") as f:
        f.write(data)

    print(f"[+] Tulip ADT successfully generated: {args.output} ({len(data)} bytes)")
    if args.dump:
        print(f"    Nodes serialized: {len(data)} bytes")

if __name__ == "__main__":
    main()
