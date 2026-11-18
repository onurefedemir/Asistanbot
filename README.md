# Asistanbot

Telegram asistan botu + **finans ajanı**.

Finans ajanı Claude üzerinde çalışır. Fiyat çeker, teknik analiz yapar, stratejileri geçmiş veride test eder (backtest) ve **sanal** portföyde al/sat yapar. Gerçek para kullanılmaz.

> ⚠️ Yatırım tavsiyesi değildir. Hiçbir sistem al/sat başarısını garanti edemez. Ajan her öneriden önce stratejinin o sembolde geçmişte nasıl çalıştığını ölçer, ama geçmiş performans geleceği garanti etmez. Gerçek parayla işlem yapmadan önce sanal portföyde haftalarca deneyin.

## Kurulum

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # sonra .env dosyasını doldurun
```

`.env` içinde:
- `TELEGRAM_BOT_TOKEN`: [@BotFather](https://t.me/BotFather)'dan alınır.
- `ANTHROPIC_API_KEY`: [platform.claude.com](https://platform.claude.com) adresinden alınır.

Finans ajanını bir kez oluşturun (kimlikleri `.env` dosyasına yazar):

```bash
python -m finance.setup_agent
```

Botu başlatın:

```bash
python main.py
```

## Kullanım

| Komut | Ne yapar |
|---|---|
| `/fiyat BTCUSDT` | Anlık fiyat |
| `/analiz THYAO.IS 1d` | RSI, MACD, SMA, Bollinger, ATR, stop/hedef önerisi |
| `/backtest ETHUSDT 4h` | 4 stratejinin komisyon dahil geçmiş performansı |
| `/portfoy` | Sanal portföy, K/Z, kazanma oranı |
| `/al BTCUSDT 5000` / `/sat BTCUSDT 0.5` | Sanal alım / satış |
| `/gecmis`, `/sifirla`, `/yeni` | İşlem geçmişi, portföyü sıfırla, ajanla yeni sohbet |

Serbest mesajlar ajana gider. Örnek: *"BTC ve ETH'yi analiz et, backtest'e göre hangisi daha mantıklı? Uygunsa 5000 ile al."*

Semboller: kripto `BTCUSDT` (Binance), BIST `THYAO.IS`, ABD `AAPL`, döviz `USDTRY=X` (Yahoo Finance).

## Yapı

```
main.py                 Telegram komutları, serbest mesajları ajana iletir
finance/market.py       Binance + Yahoo Finance fiyat/mum verisi
finance/indicators.py   Teknik indikatörler ve puanlama
finance/backtest.py     Strateji backtest'leri
finance/portfolio.py    SQLite sanal portföy
finance/tools.py        Ajanın araçları
finance/agent.py        Claude Managed Agents döngüsü (sohbet başına oturum)
finance/setup_agent.py  Ajanı oluşturur/günceller
```

Sistem istemini (`finance/agent.py`) ya da araçları değiştirirseniz `python -m finance.setup_agent` komutunu tekrar çalıştırın. Mevcut sohbetler eski sürümde kalır, yeni sürüm için `/yeni` yazın.

Testler (internet gerektirmez): `pip install pytest && python -m pytest tests`

## İkili opsiyon araştırması (`binary/`)

Pocket Option gibi platformlardaki OTC olmayan döviz çiftleri için **yalnızca araştırma ve demo**. İşlem açmaz.

```bash
python -m binary.data        # 10 çiftin son 30 günlük 1 dk verisini binary.db'ye ekler (her gün çalıştırın)
python -m binary.research    # 1056 strateji/vade/seans kombinasyonunu eğitim+test döneminde sınar
python -m binary.live        # canlı sinyal (sesli uyarı); DEMO hesapta elle işlem açın
python -m binary.live --journal   # demo sonuçlarını girin
python -m binary.live --stats     # demo kazanma oranı ve başa baş karşılaştırması
python -m binary.paper            # canlı izleyip kendi karar veren SANAL işlem motoru (tıklama yapmaz)
python -m binary.paper --max-trades 10   # 10 işlem kapanınca durur ve özet verir
python -m binary.paper --report   # sanal işlem sonuçları ve seçicinin strateji durumları
python -m binary.paper --ml       # ML stratejilerini de ekle (günde bir yeniden eğitilir)
python -m binary.ml evaluate      # ML modelinin kayan pencereli testi (14 gün eğit → ertesi gün test)
```

İlk sonuçlar: [docs/binary_research.md](docs/binary_research.md). Özet: gerçekçi girişte başa baş oranını geçen strateji bulunamadı.

**Otomatik veri toplama:** `.github/workflows/veri-topla.yml` her gün 06:17 TSİ'de GitHub'ın sunucularında çalışır (PC'nin açık olması gerekmez). Veriyi ve güncel araştırma raporlarını `data` dalına kaydeder; `main` dalına dokunmaz. En son sonuçlar: `data` dalındaki `research_delay1.txt`. Elle çalıştırmak için GitHub → Actions → "Veri topla" → Run workflow.

PC'de toplanmış veriyi kullanmak için: `git fetch origin data && git archive origin/data candles | tar -x && python -m binary.data --import-csv candles`
