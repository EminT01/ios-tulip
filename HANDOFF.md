# ios-tulip — Devir Teslim Notu

Son güncelleme: 2026-11-26

## Proje

Redmi Note 6 Pro (`tulip`, SDM636) üzerinde iOS 16.7.16 (20H392, iPhone X userland) çalıştırma.
XNU xnu-8796.141.3 tabanlı, `ios-sweet` (dip a-studio, SM7150) hattının türevi.

## Mevcut Durum

### ÇALIŞIYOR
- Boot zinciri: stock ABL → fastboot boot → shim → XNU → eMMC SDHCI → HFS+ root → launchd
- **Kilit ekranı açılıyor** (SpringBoard + backboardd ayakta, saat ilerliyor)
- eMMC okuma/yazma (50 MHz), HFS+ root mount
- SMP: `cpus=8 tulipcpu=1`
- NVT NT36672A dokunma sürücüsü: I2C okuma, event page 0x21c00, chip id `0a 00 00 72 66 03`
- HID zinciri: `sweet_hid_touch()` → `SweetHIDTouch` → backboardd (1 client)
- Assets.car (BoundingPath): **nonnil 23/31** (D22AP `/product` düğümü sayesinde)
- fsck: gerçek `com.apple.fsck` geri yüklendi
- BlueTool / bluetoothd / fairplayd.H2 döngüleri kırıldı

### ÇALIŞMIYOR / AÇIK
1. **DOKUNMA EKRANA ULAŞMIYOR (ana sorun)**
   - Kernel `TULIP HID: touch 0 down at 508,1576 (1 clients)` basıyor — koordinatlar doğru
   - backboardd 1 client ile bağlı
   - Ekran tepki vermiyor
   - Denenen: 0324 (PANEL_H 2280), 0326 (SurfaceWidth/Height 75x158mm) — build hazır, test edilmedi
2. **Boot 21 dakika** (1006-1306 s)
   - Timer doğru (HB13: cntpct == mach)
   - console 123 s + eMMC 163 s açıklanıyor, ~1000 s kayıp
   - `sweetsample` stage 0 / wakes 0 → tsleep sorunu
3. GPU yok (CPU render)
4. Wi-Fi / BT / kamera / ses / modem yok (stub'lar)

## Boot Arg'ları (çalışan set)

```
serial=3 keepsyms=1 -noprogress wdt=-1 sweettouch=0 sweetkeys=0 emmcroot=userdata
rd=emmcroot0 sdcclk=1 noreset=1 emmcrw=1 ignition_level=1 unentitled_ios_sim_launch=1
launchd_unsecure_cache=1 cs_enforcement_disable=1 sweetsample=- cpus=8 tulipcpu=1
touchprobe=3 tuliposm=1 sweetnull=- sweetfb_noconsole=1 sweetfb_hz=30
```

Önemli olanlar:
- `touchprobe=3` → NVT sürücüsü (sweettouch=0 = FTS kapalı)
- `tulipcpu=1` → SweetCPU match (SMP için ZORUNLU)
- `cpus=8` → 8 core
- `sweetfb_noconsole=1` → konsol GUI'yi kapatmaz
- `sweetnull=-` → hiçbir süreç logu console'a basılmaz (log göremezsin!)

## İmaj Üretimi

```bash
# 1) CI build (xnu/patches push edilince otomatik)
gh run list --limit 3
gh run download <RUN_ID> -n tulip-payload -D /tmp/k

# 2) payload'a cmdline yaz (offset 0x48, max 607 byte)
python3 - <<'PY'
CMD = "serial=3 ... sweetfb_hz=30"
d = bytearray(open("/tmp/k/tulip.payload","rb").read())
c = CMD.encode()
d[0x48:0x2a8] = c + b"\x00"*(0x260-len(c))
open("/tmp/p.payload","wb").write(bytes(d))
PY

# 3) imaj paketle
cd ~/ios-tulip/shim-tulip
python3 -I build.py /home/emint/boot.img tools /tmp/p.payload
# -> out/tulip-boot.img

# 4) flash
C:\platform-tools\fastboot.exe flash boot ...\tulip-boot.img
C:\platform-tools\fastboot.exe reboot
```

**KURAL:** `build.py` stock boot.img (`/home/emint/boot.img`) + payload ister.
Cmdline'ı payload'a yazmak için `mkpayload_tulip.py` KULLANMA (PowerShell katmanı
newline'ı bozuyor, sadece `serial=3` kalıyor). Python script'ten yaz.

## Rootfs (userdata) İmajı

`/home/emint/rootwork/ios16-root.img` (17 GB, HFS+)
Yedek: `ios16-root.prev.img` (19 Kasım — TEMİZ, bozulmamış)

### Bağlama (rw)
```bash
sudo bash ~/rootwork/mount-rw.sh
# bitince:
sudo sync && sudo umount /mnt/root && sudo losetup -d /dev/loop0
```

### Rootfs'te yapılan onarımlar
| Ne | Durum |
|---|---|
| `/sbin/fsck` | gerçek `com.apple.fsck` (71008 byte) geri kondu, mount kopyası `fsck.mountcopy` olarak yedek |
| `launchd.plist` | `com.apple.BlueTool` job kaldırıldı, bluetoothd+fairplayd.H2 `KeepAlive` silindi, `ThrottleInterval=60` |
| Yedekler | `/root/launchd.plist.pre-jobfix`, `/root/launchd.plist.pre-fsck` |

### Rootfs script'leri (`~/rootwork/`)
- `mount-rw.sh` — rw bağla + doğrula
- `find-jobs.sh` — launchd job'larını listele
- `fix-jobs.sh [apply]` — BlueTool/BT/fairplayd döngülerini kır
- `restore-fsck.sh [apply]` — eski imajdan gerçek fsck al
- `restore-launchdplist.sh [apply]` — eski imajdan orijinal launchd.plist al
- `check-assets.sh` — Assets.car karşılaştır
- `carparse.py` — BOMStore analizi

**KURAL:** `plistlib.dumps(FMT_BINARY)` ile launchd.plist YENİDEN YAZMA → byte
farkı launchd'yi bozar, boot panic eder (`identity mismatch for a boot-task`).

## Patch Sistemi

`~/ios-tulip/xnu/patches/` — numaralı, sırayla uygulanır. Son: **0326**.

### KRİTİK KURALLAR
1. **`diff -U0` ASLA kullanma** — context'siz patch yanlış yere düşer
2. **`diff -U3` kullan**, hunk'ı iki sağlam çıpa arasına bağla
3. Yeni patch, **kendinden önceki patch'ler uygulanmış ağaçtan** üretilmeli
4. **Push etmeden önce doğrula:**
   - `patch -p1 --forward --dry-run` → EXIT=0
   - gerçek `patch -p1 --forward` → EXIT=0
   - `git apply --check` (CI yöntemi)
   - `grep -n` + `sed -n` ile eklenen satırın YERİNİ gözle doğrula
   - 500+ satır kaydırılmış kopyada da test et (offset almalı)
5. **Push için kullanıcıdan onay iste**

### Son patch'ler
| # | Ne |
|---|---|
| 0320 | Storm freni: core başına 100k/1M eşik, 25/10 Hz'e düş |
| 0321 | Secondary redistributor'da PPI 30 kapat |
| 0322 | HB11 (idle ms + bench), HB12 (APCS rcgr) |
| 0323 | tsleep ölçümü (HB13) |
| 0324 | `SWEET_TOUCH_PANEL_H` 2160 → 2280 |
| 0325 | touch log'una client sayısı |
| 0326 | `SurfaceWidth/Height` 68x151 → 75x158 mm |

## Teşhis Satırları (HB)

`tulip_sdhci_read_blocks` içindeki heartbeat bloğu, 20 s'de bir basar.
**`sweetsample=-` ise ÇIKMAZ.**

| HB | İçerik |
|---|---|
| HB2 | irq timer/ipi/other/spurious |
| HB3 | cntv ctl, cval-cnt, gicr grp/enab/pend |
| HB7 | timer irqs per CPU (8) |
| HB8 | storm snapshot (cntv/cntp ctl, cval-ct, frq) |
| HB10 | NVT dokunma: stage, ack, chip, downs, last x,y, irq |
| **HB11** | idle ms per core (8) + wakes, ALU/mem benchmark |
| **HB12** | APCS rcgr: silver cmd/cfg, gold cmd/cfg (`tuliposm=1`) |
| **HB13** | cntfrq, cntpct, mach ms — timer doğrulama |
| HB | up s, sampler stage, wakes, eMMC reads |

## Ölçülen Değerler (26 Kasım boot)

```
HB11: idle ms 0 0 0 0 0 0 0 0 wakes 0        ← cpus=8 tulipcpu=1 YOKKEN
HB12: rcgr silver cmd 2 cfg 501 | gold cmd 2 cfg 401
HB13: cntfrq 19200000 cntpct ... mach 130741 ms
HB10: nvt stage 4 ack 2 chip 7266 rc 0 page 21c00 state 0 max 1000,2280
      polls 8815 fail 1 downs 55 last 0,1403 irq 0
PERF: cpus online 1/1, up 1306 s, console 123507 ms, eMMC 163063 ms
NVT: chip id try 0 rc 0  0a 00 00 72 66 03
NVT: event page 0x21c00 reset state a1; fwinfo rc 0 fw 13/ec
     x_num 18 y_num 36 max x 1000 y 2280
```

## Referans Projeler

| Proje | Ne için |
|---|---|
| `~/work/bt/whyred2` | SDM636 eMMC, GCC clock, HFSX (Faz 1-2) |
| `ios-sweet` (dipa-studio) | Tulip hattının tabanı — VINCE config, IOKit iskeleti |
| `ios-topaz` (MakrSas) | Root mount, launchd, backboardd, IOSurface (Faz 2-3) |
| `HackiOS` / `OOSEX` | Adreno + Mesa, tweak injection (Faz 4) |

**sweet'in NOTES.md önemli notları:**
- `0061`: AppleCLCD 1125x2436 sunar, panel 1080x2400, **touch aynı şekilde eşlenir**
- `0071`: Edge touch (48 px) → `kIOHIDDigitizerEventFromEdgeTip`,
  EventMask `0xb0007` bit 0x800/0x1000/0x2000/0x40000 (UIKit okur)
- `0063`: Goodix GT9896 I2C FIFO **byte-swap** hatası (register adresi ters gidiyordu)

## Sıradaki Adımlar (öncelik)

1. **0326'yı test et** → dokunma çalışıyor mu?
2. Çalışmazsa:
   a. `sweetnull=backboardd` yap, `TULIP HID: touch ... (N clients)` gör
   b. EventMask'i sweet 0071 gibi düzelt (0327)
   c. `kIOHIDEventFieldDigitizerIsDisplayIntegrated` ekle
3. Boot süresi: `sweetsample` stage/wakes sorununu çöz (tsleep vs tick)
4. SMP doğrula: `HB11 idle ms` 0'dan farklı olmalı

## Dosya Konumları

- Repo: `~/ios-tulip`
- Patch'ler: `~/ios-tulip/xnu/patches/` (0326 son)
- Kernel: CI artifact `tulip-payload` → `tulip.payload`
- Stock boot: `/home/emint/boot.img` (64 MB, ANDROID! header)
- Rootfs: `~/rootwork/ios16-root.img` + `.prev.img` (yedek)
- Rootfs script'leri: `~/rootwork/*.sh`, `carparse.py`
- Work ağaçları: `~/work/bt/` (bt319x = temel referans)
- fastboot: `C:\platform-tools\fastboot.exe`
