import asyncio
import logging
import os

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

from finance import backtest, indicators, market
from finance.agent import FinanceAgent
from finance.portfolio import Portfolio

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise SystemExit("TELEGRAM_BOT_TOKEN tanımlı değil. .env.example dosyasını .env olarak kopyalayıp doldurun.")

portfolio = Portfolio(os.environ.get("FINANCE_DB", "finance.db"))
agent = FinanceAgent(portfolio)

HELP = """Merhaba! Ben yardımcı asistan botunuzum. Finans komutları:

/fiyat BTCUSDT – anlık fiyat
/analiz THYAO.IS [1d|4h|1h] – teknik analiz
/backtest ETHUSDT [1d|4h|1h] – stratejilerin geçmiş performansı
/portfoy – sanal portföy
/al BTCUSDT 5000 – sanal alım (tutar)
/sat BTCUSDT [0.5] – sanal satış (oran, varsayılan tamamı)
/gecmis – son işlemler
/sifirla – sanal portföyü sıfırla
/yeni – ajanla yeni konuşma başlat

Ya da doğrudan yazın: "BTC'yi analiz et, mantıklıysa 5000 ile al" gibi.
Tüm işlemler SANALdır, gerçek para kullanılmaz. Yatırım tavsiyesi değildir."""


async def reply(update: Update, text: str):
    # Telegram mesaj sınırı 4096 karakter
    for i in range(0, len(text), 4000):
        await update.message.reply_text(text[i : i + 4000])


def fmt(d: dict) -> str:
    lines = []
    for k, v in d.items():
        if isinstance(v, list):
            lines.append(f"{k}:")
            lines += [f"  • {x}" for x in v]
        elif v is not None:
            lines.append(f"{k}: {v}")
    return "\n".join(lines)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP)


async def fiyat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("Kullanım: /fiyat BTCUSDT")
    sym = context.args[0].upper()
    try:
        price = await asyncio.to_thread(market.get_price, sym)
        await update.message.reply_text(f"{sym}: {price:,.6g}")
    except Exception as e:
        await update.message.reply_text(f"Fiyat alınamadı: {e}")


async def analiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("Kullanım: /analiz BTCUSDT [1d|4h|1h]")
    sym = context.args[0].upper()
    interval = context.args[1] if len(context.args) > 1 else "1d"
    try:
        df = await asyncio.to_thread(market.get_candles, sym, interval, 400)
        await reply(update, f"📊 {sym} ({interval})\n" + fmt(indicators.analyze(df)))
    except Exception as e:
        await update.message.reply_text(f"Analiz yapılamadı: {e}")


async def backtest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("Kullanım: /backtest BTCUSDT [1d|4h|1h]")
    sym = context.args[0].upper()
    interval = context.args[1] if len(context.args) > 1 else "1d"
    try:
        df = await asyncio.to_thread(market.get_candles, sym, interval, 1000)
        results = backtest.compare(df)
        out = [f"🧪 {sym} ({interval}) – {results[0]['period']}, komisyon dahil"]
        for r in results:
            out.append(
                f"\n{r['strategy']}: getiri %{r['total_return_pct']} (al-tut %{r['buy_and_hold_pct']}), "
                f"işlem {r['trades']}, kazanma %{r['win_rate_pct']}, max DD %{r['max_drawdown_pct']}"
                + (f"\n  ⚠️ {r['warning']}" if r["warning"] else "")
            )
        out.append("\nGeçmiş performans geleceği garanti etmez.")
        await reply(update, "\n".join(out))
    except Exception as e:
        await update.message.reply_text(f"Backtest yapılamadı: {e}")


async def portfoy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    s = portfolio.summary(chat_id)
    prices = {}
    for p in s["positions"]:
        try:
            prices[p["symbol"]] = await asyncio.to_thread(market.get_price, p["symbol"])
        except Exception:
            pass
    s = portfolio.summary(chat_id, prices)
    lines = [
        f"💼 Nakit: {s['cash']:,.2f}",
        f"Toplam değer: {s['total_value']:,.2f} (%{s['total_return_pct']})",
        f"Gerçekleşen K/Z: {s['realized_pnl']:,.2f} | Kapanan işlem: {s['closed_trades']}"
        + (f" | Kazanma %{s['win_rate_pct']}" if s["win_rate_pct"] is not None else ""),
    ]
    for p in s["positions"]:
        lines.append(f"• {p['symbol']}: {p['qty']:.6g} @ {p['avg_price']:,.6g} → {p['price']:,.6g} (%{p['unrealized_pnl_pct']})")
    await update.message.reply_text("\n".join(lines))


async def al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        return await update.message.reply_text("Kullanım: /al BTCUSDT 5000")
    sym = context.args[0].upper()
    try:
        price = await asyncio.to_thread(market.get_price, sym)
        t = portfolio.buy(update.effective_chat.id, sym, price, float(context.args[1]), "manuel")
        await update.message.reply_text(
            f"✅ SANAL ALIM {sym}: {t['qty']:.6g} adet @ {price:,.6g}, kalan nakit {t['cash_left']:,.2f}"
        )
    except Exception as e:
        await update.message.reply_text(f"Alım yapılamadı: {e}")


async def sat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("Kullanım: /sat BTCUSDT [0.5]")
    sym = context.args[0].upper()
    frac = float(context.args[1]) if len(context.args) > 1 else 1.0
    try:
        price = await asyncio.to_thread(market.get_price, sym)
        t = portfolio.sell(update.effective_chat.id, sym, price, frac, "manuel")
        await update.message.reply_text(
            f"✅ SANAL SATIŞ {sym}: {t['qty']:.6g} adet @ {price:,.6g}, K/Z {t['realized_pnl']:,.2f}"
        )
    except Exception as e:
        await update.message.reply_text(f"Satış yapılamadı: {e}")


async def gecmis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = portfolio.history(update.effective_chat.id, 15)
    if not rows:
        return await update.message.reply_text("Henüz işlem yok.")
    await reply(update, "\n".join(
        f"{r['time']} {r['side']} {r['symbol']} {r['qty']:.6g} @ {r['price']:,.6g}"
        + (f" K/Z {r['realized_pnl']:,.2f}" if r["side"] == "SELL" else "")
        + (f" – {r['reason']}" if r["reason"] else "")
        for r in rows
    ))


async def sifirla(update: Update, context: ContextTypes.DEFAULT_TYPE):
    portfolio.reset(update.effective_chat.id)
    await update.message.reply_text("Sanal portföy sıfırlandı.")


async def yeni(update: Update, context: ContextTypes.DEFAULT_TYPE):
    agent.reset(update.effective_chat.id)
    await update.message.reply_text("Ajanla yeni bir konuşma başlatıldı.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not agent.enabled:
        return await update.message.reply_text(
            "Finans ajanı henüz kurulmadı. Komutlar için /start yazın."
        )
    await context.bot.send_chat_action(update.effective_chat.id, "typing")
    try:
        answer = await asyncio.to_thread(agent.ask, update.effective_chat.id, update.message.text)
    except Exception as e:
        logging.exception("Ajan hatası")
        answer = f"Ajan şu an yanıt veremedi: {type(e).__name__}"
    await reply(update, answer)


app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler(["start", "yardim"], start))
app.add_handler(CommandHandler("fiyat", fiyat))
app.add_handler(CommandHandler("analiz", analiz))
app.add_handler(CommandHandler("backtest", backtest_cmd))
app.add_handler(CommandHandler("portfoy", portfoy))
app.add_handler(CommandHandler("al", al))
app.add_handler(CommandHandler("sat", sat))
app.add_handler(CommandHandler("gecmis", gecmis))
app.add_handler(CommandHandler("sifirla", sifirla))
app.add_handler(CommandHandler("yeni", yeni))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

app.run_polling()
