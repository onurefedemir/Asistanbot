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
