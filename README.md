# Asistanbot – Araba Fiyat Takip Botu 🚗

**sahibinden.com** ve **arabam.com**'daki ilanları tarayan, en ucuz ve piyasanın altındaki
ilanları bulan, fiyat düşünce ya da yeni fırsat çıkınca **Telegram**'dan haber veren bot.

## Özellikler

- 🔎 İki siteyi tek aramada tarar, sonuçları tek listede birleştirir
- 💰 **En ucuz** ilanları listeler
- 💎 **Fırsat analizi**: aynı aramadaki ilanlardan yıl + km'ye göre "beklenen fiyat" hesaplar
  (basit doğrusal regresyon) ve piyasanın en çok altındaki ilanları bulur.
  2015 model 200 bin km bir araç ucuz diye "fırsat" sayılmaz.
- 📉 **Fiyat takibi**: her ilanın fiyat geçmişini tutar, fiyat düşünce bildirir
- 🆕 **Yeni ilan bildirimi**: piyasanın %10+ altında yeni ilan düşerse 🔥 ile işaretler
- 🗑 Yayından kalkan (satılan) ilanları otomatik pasife alır
- 🔐 İsteğe bağlı kullanıcı kısıtlaması (`ALLOWED_USER_IDS`)

## Kurulum

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                  # sonra .env içine TELEGRAM_TOKEN yazın
python main.py
```

Token'ı Telegram'da **@BotFather** → `/newbot` ile alırsınız. Token'ı asla koda yazıp
GitHub'a göndermeyin; `.env` dosyası `.gitignore`'dadır.

## Telegram komutları

| Komut | Açıklama |
|---|---|
| `/takip renault clio fiyat=-900bin yil=2018- km=120000` | Yeni takip ekler ve hemen tarar |
| `/liste` | Takipleriniz ve her birindeki en düşük fiyat |
| `/enucuz 1` | 1 numaralı takipteki en ucuz ilanlar |
| `/firsat 1` | Yıl/km'ye göre en avantajlı ilanlar |
| `/gecmis 42` | 42 numaralı ilanın fiyat geçmişi |
| `/kontrol` | Takipleri şimdi tara |
| `/sil 1` | Takibi sil |

**Filtre yazımı:** `fiyat=MIN-MAX`, `yil=MIN-MAX`, `km=MAX`. Bir tarafı boş bırakabilirsiniz
(`yil=2018-` = 2018 ve sonrası). Tek değer: `fiyat=900bin` → en fazla, `yil=2018` → en az.
Tutarlar `900bin`, `1.2m`, `1,5milyon`, `850.000` şeklinde yazılabilir.

## Telegram'sız deneme (CLI)

```bash
python -m asistanbot.cli renault clio fiyat=-900bin yil=2018-
```

Site yapısı değişirse, sayfayı tarayıcıdan "Farklı kaydet" ile indirip ayrıştırıcıyı deneyin:

```bash
python -m asistanbot.cli --parse arabam kayitli_sayfa.html
python -m asistanbot.cli --parse sahibinden kayitli_sayfa.html
```

## Ayarlar (`.env`)

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `CHECK_INTERVAL_MIN` | 60 | Otomatik kontrol aralığı (dakika) |
| `MAX_PAGES` | 2 | Site başına çekilecek sayfa (sayfa başı 50 ilan, fiyata göre artan) |
| `REQUEST_DELAY` | 4 | İstekler arası bekleme (sn) |
| `FETCHER` | httpx | `playwright` = gerçek tarayıcıyla çek |
| `MIN_DROP_RATIO` | 0.01 | Bu oranın altındaki fiyat düşüşleri bildirilmez |
| `DEAL_RATIO` | 0.90 | Beklenen fiyatın %90'ı ve altı = fırsat |
| `ALLOWED_USER_IDS` | (boş) | Botu kullanabilecek Telegram ID'leri |

## sahibinden.com bot koruması

sahibinden.com otomatik isteklere karşı sıkı bir koruma kullanır; düz HTTP istekleri
(özellikle sunucu/VPS IP'lerinden) çoğunlukla engellenir. Bot bu durumda çökmez, uyarı verir
ve arabam.com ile devam eder. Engellenirseniz:

```bash
pip install playwright && playwright install chromium
# .env → FETCHER=playwright
```

Ev internetinizden düşük sıklıkla çalıştırmak (60+ dk) en sorunsuz yöntemdir.

## ⚠️ Yasal not

Her iki sitenin kullanım koşulları otomatik veri toplamayı kısıtlar. Bu proje **kişisel,
düşük hacimli** kullanım içindir: sık istek atmayın, verileri yeniden yayınlamayın veya
ticari amaçla kullanmayın. Sorumluluk kullanıcıya aittir.

## Proje yapısı

```
main.py                    # botu başlatır
asistanbot/
  bot.py                   # Telegram komutları + periyodik kontrol
  tracker.py               # tarama → kaydetme → yeni/düşüş/fırsat tespiti
  analysis.py              # yıl/km'ye göre beklenen fiyat modeli
  db.py                    # SQLite: takipler, ilanlar, fiyat geçmişi
  commands.py              # /takip metnini ayrıştırma
  formatting.py            # Telegram mesajları
  scrapers/
    base.py                # HTTP/Playwright çekici, ortak ayrıştırma yardımcıları
    sahibinden.py
    arabam.py              # tablo → JSON-LD → genel yedek ayrıştırıcı
tests/                     # pytest
```

Yeni site eklemek için `scrapers/base.py` içindeki `Scraper` sınıfından türetip
`build_url` ve `parse` yazın, `scrapers/__init__.py` içindeki `SCRAPERS` listesine ekleyin.

## Test

```bash
pip install pytest && python -m pytest -q
```
