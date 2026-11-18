# Tulip — 0263 denetimi ve sonraki adımlar (2026-11-18)

## Durum

| Öğe | Durum |
|---|---|
| CI `44204099520` (0263) | ✅ build 14m25s + payload 1m9s, kernel artefaktı sağlam |
| `0263` patch başı çift header | ✅ düzeltildi (`0506e50`) |
| `0264` (kart R1 hataları) | ✅ eklendi, 3 yoldan doğrulandı |
| CI `44208750469` | 🔄 derleniyor |
| Yerel imaj | ✅ `~/tulip-0330.img` — `sdcclk=1`, **`sdcmhz` yok** (25 MHz) |
| Telefon | ⛔ bağlı değil (`fastboot devices` boş) |

## 0263 denetim sonucu

1. **Çift `---`/`+++` başlığı.** `patch` yutuyor, `git apply` "corrupt patch"
   verebilir. Kaldırıldı.
2. **Doğrulama tabanı yanlıştı.** `verify260` 0208 öncesi (içinde `se.clk_mhz`
   yok) → hunk 4 orada FAILED. Gerçek kontrol: `vtFF`ten 0263 geri çıkarıldı
   (`un263.py` → `base263.c`), patch yeniden uygulandı → **birebir aynı dosya**.
   Yani CI artefaktı geçerli.
3. **Sıra doğru:** 400 kHz → EXT_CSD → 25 MHz → BUS_WIDTH=8 → HS_TIMING=1 → 50 MHz.
4. **Tek gerçek kusur:** `sdcmhz=50` verilirse 25 MHz adımında da `0x210f`
   yazılıyor, yani HS_TIMING'den **önce** kart 50 MHz'e çıkıyor (Default Speed
   26 MHz bütçesi aşılır). `sdcmhz` kaldırıldı; ileride 50 MHz gerekirse ayrı
   patch ile "sadece 50M adımında yükselt" yapılmalı.

## 0264 — kartın kendi R1 hataları

`sdhci_cmd()` yalnızca `SDHCI_INT_ERR`a bakıyordu; bu **denetleyicinin** hata
bitleridir. Kartın kendi cevabındaki R1 hata bitleri (illegal-command,
com-crc, cc-error, wp-violation, block-len) hiç okunmuyordu.

Sonuç: CMD6 EXT_CSD yazımı kart tarafından reddedilse bile "başarılı"
görünüyor → host 8-bit'e geçiyor → sonraki blok okuması kartın hiç switch
etmediği genişlikte çerçeveleniyor. **`U5Root` corruption'ının şekli bu.**

`sdhci_resp_check()` eklendi: kısa (R1/R6/R7) cevaplarda hata biti varsa
isimle yazıyor. Davranış değişmiyor, sadece görünürlük — bu yüzden boot'u
riske atmıyor.

## Teşhis için: log'da ne arayacaksın

```
TULIP SDHCI: sdcc1_apps rate 25 MHz: RCG CMD 0x00000001 CFG 0x0000211f
```
`CFG 0x0000211f` görmen lazım. `0x2017` görürsen saat hâlâ 400 kHz.

```
TULIP SDHCI: command 6: card R1 error 0x.... (cc-error)
```
0264'ün yeni satırı. Bu çıkarsa corruption'ın kaynağı kesin bu.

## Sıradaki işler

1. Telefonu bağla → `bash flash.sh ~/tulip-0330.img`
2. Boot süresini ölç (1.5 saat → beklenen 2-3 dk), yukarıdaki iki satırı doğrula.
3. 25 MHz tutarsa 50 MHz'i "sadece son adımda" patch'i olarak ekle (0265).
4. `U5Root` corruption 0264 ile hâlâ sürüyorsa: ACMD12 sonrası `BYTE_COUNT`
   ve `SDHCI_INT_ACMD12ERR` (0x01000000) doğrulaması.
5. `opacity` SIGFPE · backboardd HID döngüsü · `xpcproxy [com.apple.peopled]` takılması.

## HS200 — şimdilik kapsam dışı (karar)

HS200 (200 MHz) **yapılmayacak**. Gerekçe:

- 1.8 V sinyal + CMD21 tuning + kilitli Qualcomm DLL gerekir.
- Yanlış tuning penceresi, **kök imaj read-write mount'lu iken** bozuk yazma
  üretebilir. HFS+ `U5Root` corruption'ı zaten açık bir sorunken bu riski
  büyütmenin anlamı yok.
- Sürücüde bugün tuning/DDR/HS200 kodu **hiç yok** (`tulip_sdhci.c` içinde tek
  geçen yer yorum satırları), yani kazara açılma riski de yok. Tablo başına
  "DO NOT SELECT TULIP_GCC_RATE_100M" uyarısı eklendi (0265).

**Güvenli ara basamak — DDR52:** `HS_TIMING=0x04`, aynı 52 MHz saat,
çift kenar (double pumped), **tuning ve DLL gerekmez**. Kazanç 2×. HS200'nin
aksine root'u bozacak bir mekanizması yok: yanlış giderse kart CMD6'da
`SWITCH_ERROR` döner ve mevcut kod bunu `EIO` olarak görüp 25 MHz HS'te kalır.
İstenirse ilk sürümde `sdhddr=1` boot-arg arkasına konur.

Sıra: **önce boot'u doğrula → sonra DDR52 → HS200'ü hiç yapma.**
