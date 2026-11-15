from __future__ import annotations

import asyncio
import logging
from functools import wraps

from telegram import LinkPreviewOptions, Update
from telegram.constants import ParseMode
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes

from . import formatting as fmt
from .commands import USAGE, ParseError, parse_takip
from .config import config
from .db import DB
from .models import fmt_num
from .tracker import check_search

log = logging.getLogger(__name__)
db = DB()
_check_lock = asyncio.Lock()  # aynı anda tek tarama (siteleri yormamak için)

HELP = (
    "🚗 <b>Araba Fiyat Takip Botu</b>\n"
    "sahibinden.com ve arabam.com'u tarar, en ucuz ve piyasanın altındaki ilanları bulur, "
    "fiyat düşünce ve yeni fırsat ilan çıkınca haber verir.\n\n"
    "<b>Komutlar</b>\n"
    "/takip – yeni takip ekle (detay için sadece /takip yazın)\n"
    "/liste – takiplerim\n"
    "/enucuz &lt;no&gt; – en ucuz ilanlar\n"
    "/firsat &lt;no&gt; – yıl/km'ye göre en avantajlı ilanlar\n"
    "/gecmis &lt;ilan no&gt; – bir ilanın fiyat geçmişi\n"
    "/kontrol – takipleri şimdi tara\n"
    "/sil &lt;no&gt; – takibi sil\n\n"
    f"Takipler her {config.check_interval_min} dakikada bir otomatik kontrol edilir."
)


async def send(update: Update, text: str) -> None:
    for chunk in _chunks(text):
        await update.effective_message.reply_text(
            chunk, parse_mode=ParseMode.HTML, link_preview_options=LinkPreviewOptions(is_disabled=True)
        )


def _chunks(text: str, size: int = 3900):
    while len(text) > size:
        cut = text.rfind("\n", 0, size)
        cut = cut if cut > 0 else size
        yield text[:cut]
        text = text[cut:]
    yield text


def restricted(fn):
    @wraps(fn)
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id if update.effective_user else None
        if config.allowed_user_ids and uid not in config.allowed_user_ids:
            await update.effective_message.reply_text(f"Bu botu kullanma yetkiniz yok. (ID: {uid})")
            return
        return await fn(update, ctx)

    return wrapper


def _search_arg(update: Update, ctx) -> int | None:
    if ctx.args and ctx.args[0].lstrip("#").isdigit():
        return int(ctx.args[0].lstrip("#"))
    searches = db.searches(update.effective_chat.id)
    return searches[0].id if len(searches) == 1 else None


# ------------------------------------------------------------------ handlers


@restricted
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await send(update, HELP)


@restricted
async def takip(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        return await send(update, USAGE)
    try:
        search = parse_takip(ctx.args)
    except ParseError as e:
        return await send(update, f"❌ {e}\n\n{USAGE}")
    search.chat_id = update.effective_chat.id
    db.add_search(search)
    await send(update, f"✅ Takip #{search.id} eklendi: <b>{search.describe()}</b>\nİlk tarama yapılıyor, biraz sürebilir…")
    async with _check_lock:
        rep = await asyncio.to_thread(check_search, db, search)
    rows = db.active_listings(search.id)
    msg = fmt.cheapest(search, rows, 5)
    if len(rows) >= 5:
        msg += "\n\n" + fmt.deals(search, rows, 5)
    if rep.errors:
        msg += "\n\n⚠️ " + "\n⚠️ ".join(rep.errors)
    await send(update, msg)


@restricted
async def liste(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    searches = db.searches(update.effective_chat.id)
    if not searches:
        return await send(update, "Henüz takip yok. /takip ile ekleyin.")
    lines = []
    for s in searches:
        rows = db.active_listings(s.id)
        best = f"en ucuz {fmt_num(rows[0]['price'])} TL" if rows else "ilan yok"
        lines.append(f"<b>#{s.id}</b> {s.describe()} — {len(rows)} ilan, {best}")
    await send(update, "📋 <b>Takipleriniz</b>\n" + "\n".join(lines))


@restricted
async def enucuz(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    sid = _search_arg(update, ctx)
    s = db.get_search(sid, update.effective_chat.id) if sid else None
    if not s:
        return await send(update, "Takip numarası verin: <code>/enucuz 1</code> (bkz. /liste)")
    await send(update, fmt.cheapest(s, db.active_listings(s.id), 15))


@restricted
async def firsat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    sid = _search_arg(update, ctx)
    s = db.get_search(sid, update.effective_chat.id) if sid else None
    if not s:
        return await send(update, "Takip numarası verin: <code>/firsat 1</code> (bkz. /liste)")
    await send(update, fmt.deals(s, db.active_listings(s.id), 15))


@restricted
async def gecmis(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args or not ctx.args[0].lstrip("#").isdigit():
        return await send(update, "İlan numarası verin: <code>/gecmis 42</code> (listelerdeki #numara)")
    row = db.get_listing(int(ctx.args[0].lstrip("#")))
    if not row or row["chat_id"] != update.effective_chat.id:
        return await send(update, "İlan bulunamadı.")
    hist = db.history(row["id"])
    lines = [f"{h['seen_at'][:16].replace('T', ' ')} — {fmt_num(h['price'])} TL" for h in hist]
    change = row["price"] - row["first_price"]
    status = "aktif" if row["active"] else "yayından kalktı"
    await send(
        update,
        fmt.listing_line(row)
        + f"\n\n📈 <b>Fiyat geçmişi</b> ({status})\n"
        + "\n".join(lines)
        + f"\n\nİlk görülme: {fmt_num(row['first_price'])} TL · değişim: {'+' if change > 0 else ''}{fmt_num(change) if change >= 0 else '−' + fmt_num(-change)} TL",
    )


@restricted
async def sil(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args or not ctx.args[0].lstrip("#").isdigit():
        return await send(update, "Takip numarası verin: <code>/sil 1</code>")
    ok = db.delete_search(int(ctx.args[0].lstrip("#")), update.effective_chat.id)
    await send(update, "🗑 Silindi." if ok else "Takip bulunamadı.")


@restricted
async def kontrol(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    searches = db.searches(update.effective_chat.id)
    if not searches:
        return await send(update, "Takip yok.")
    await send(update, f"🔄 {len(searches)} takip taranıyor…")
    any_news = False
    for s in searches:
        async with _check_lock:
            rep = await asyncio.to_thread(check_search, db, s)
        if text := fmt.report(rep):
            any_news = True
            await send(update, text)
    if not any_news:
        await send(update, "Yeni bir gelişme yok. 👍")


# ------------------------------------------------------------------ periodic job


async def periodic_check(ctx: ContextTypes.DEFAULT_TYPE):
    for s in db.searches():
        try:
            async with _check_lock:
                rep = await asyncio.to_thread(check_search, db, s)
        except Exception:
            log.exception("takip #%s kontrol hatası", s.id)
            continue
        text = fmt.report(rep)
        if text and (rep.has_news or rep.errors):
            for chunk in _chunks(text):
                await ctx.bot.send_message(
                    s.chat_id, chunk, parse_mode=ParseMode.HTML, link_preview_options=LinkPreviewOptions(is_disabled=True)
                )
        await asyncio.sleep(config.request_delay)


def build_app() -> Application:
    if not config.telegram_token:
        raise SystemExit("TELEGRAM_TOKEN tanımlı değil. .env.example dosyasını .env olarak kopyalayıp doldurun.")
    app = ApplicationBuilder().token(config.telegram_token).build()
    for name, fn in {
        "start": start, "yardim": start, "help": start, "takip": takip, "liste": liste, "enucuz": enucuz,
        "firsat": firsat, "gecmis": gecmis, "sil": sil, "kontrol": kontrol,
    }.items():  # fmt: skip
        app.add_handler(CommandHandler(name, fn))
    app.job_queue.run_repeating(periodic_check, interval=config.check_interval_min * 60, first=120)
    return app


def run() -> None:
    logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    build_app().run_polling()
