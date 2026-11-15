"""Telegram mesaj metinleri (HTML parse_mode)."""

from __future__ import annotations

from html import escape
from typing import Mapping, Sequence

from .analysis import rank_deals
from .models import Search, fmt_num
from .tracker import Report

SRC = {"sahibinden": "🟡 sahibinden", "arabam": "🔵 arabam"}


def listing_line(r: Mapping, ratio: float | None = None) -> str:
    bits = [f"<b>{fmt_num(r['price'])} TL</b>"]
    if r["year"]:
        bits.append(str(r["year"]))
    if r["km"] is not None:
        bits.append(f"{fmt_num(r['km'])} km")
    if r["location"]:
        bits.append(escape(r["location"]))
    line = " · ".join(bits)
    if ratio is not None:
        pct = (1 - ratio) * 100
        line += f" · {'🔥 piyasanın %' + f'{pct:.0f} altı' if pct > 0 else 'piyasa üstü %' + f'{-pct:.0f}'}"
    title = escape((r["title"] or "")[:70])
    return f"#{r['id']} {SRC.get(r['source'], r['source'])} — <a href=\"{escape(r['url'])}\">{title}</a>\n   {line}"


def cheapest(search: Search, rows: Sequence[Mapping], limit: int = 10) -> str:
    if not rows:
        return f"🔎 <b>{escape(search.describe())}</b>\nAktif ilan bulunamadı."
    prices = [r["price"] for r in rows]
    head = (
        f"🔎 <b>{escape(search.describe())}</b> (takip #{search.id})\n"
        f"{len(rows)} aktif ilan · en düşük {fmt_num(min(prices))} TL · "
        f"ortalama {fmt_num(sum(prices) / len(prices))} TL\n\n<b>En ucuzlar:</b>"
    )
    return head + "\n" + "\n".join(listing_line(r) for r in rows[:limit])


def deals(search: Search, rows: Sequence[Mapping], limit: int = 10) -> str:
    ranked = rank_deals(rows, limit)
    if not ranked:
        return "Analiz için yeterli ilan yok."
    return (
        f"💎 <b>Fırsatlar — {escape(search.describe())}</b>\n"
        "<i>Yıl ve km'ye göre beklenen fiyatın en altındakiler</i>\n\n"
        + "\n".join(listing_line(r, ratio) for r, ratio in ranked)
    )


def report(rep: Report) -> str | None:
    s = rep.search
    parts: list[str] = []
    if rep.drops:
        parts.append("📉 <b>Fiyatı düşenler:</b>")
        for r in rep.drops[:10]:
            parts.append(
                listing_line(r) + f"\n   <s>{fmt_num(r['prev_price'])}</s> → {fmt_num(r['price'])} TL "
                f"(−{fmt_num(r['prev_price'] - r['price'])})"
            )
    if rep.deals:
        parts.append("🔥 <b>Yeni fırsat ilanlar:</b>")
        parts += [listing_line(r, ratio) for r, ratio in rep.deals[:10]]
    deal_ids = {r["id"] for r, _ in rep.deals}
    other_new = [r for r in rep.new if r["id"] not in deal_ids]
    if other_new and not rep.first_run:
        parts.append(f"🆕 <b>Yeni ilanlar ({len(other_new)}):</b>")
        parts += [listing_line(r) for r in sorted(other_new, key=lambda r: r["price"])[:5]]
    if rep.errors:
        parts.append("⚠️ " + "\n⚠️ ".join(escape(e) for e in rep.errors))
    if not parts:
        return None
    return f"🚗 <b>Takip #{s.id}: {escape(s.describe())}</b>\n\n" + "\n".join(parts)
