"""Telegram olmadan deneme:  python -m asistanbot.cli renault clio fiyat=-900bin yil=2018-

--html-dosya ile kaydedilmiş bir sayfayı ayrıştırabilirsiniz (seçici testi için):
  python -m asistanbot.cli --parse arabam sayfa.html
"""

from __future__ import annotations

import argparse
import logging
import sys

from .analysis import rank_deals
from .commands import ParseError, parse_takip
from .db import DB
from .models import fmt_num
from .scrapers import SCRAPERS
from .tracker import check_search


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="asistanbot.cli")
    p.add_argument("args", nargs="*", help="marka model [fiyat=..] [yil=..] [km=..]")
    p.add_argument("--parse", nargs=2, metavar=("SITE", "HTML"), help="kayıtlı HTML dosyasını ayrıştır")
    p.add_argument("--db", default=":memory:", help="veritabanı (varsayılan: bellek)")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if a.parse:
        site, path = a.parse
        sc = next((s for s in SCRAPERS if s.name == site), None)
        if not sc:
            print("site: " + ", ".join(s.name for s in SCRAPERS))
            return 2
        items = sc.parse(open(path, encoding="utf-8").read())
        for l in items:
            print(f"{fmt_num(l.price):>12} TL  {l.year or '?':>4}  {fmt_num(l.km):>9} km  {l.title[:60]}  {l.url}")
        print(f"\n{len(items)} ilan ayrıştırıldı.")
        return 0 if items else 1

    try:
        search = parse_takip(a.args)
    except ParseError as e:
        print(e)
        return 2
    search.chat_id = 0
    db = DB(a.db)
    db.add_search(search)
    rep = check_search(db, search)
    rows = db.active_listings(search.id)
    print(f"\n{search.describe()} — {rep.per_source} — toplam {len(rows)} ilan")
    for e in rep.errors:
        print("UYARI:", e)
    print("\nEn ucuz 10:")
    for r in rows[:10]:
        print(f"  {fmt_num(r['price']):>12} TL  {r['year'] or '?'}  {fmt_num(r['km'])} km  [{r['source']}] {r['title'][:50]}  {r['url']}")
    print("\nFırsatlar (beklenen fiyata göre):")
    for r, ratio in rank_deals(rows, 10):
        print(f"  %{(1 - ratio) * 100:+5.0f}  {fmt_num(r['price']):>12} TL  {r['year']}  {fmt_num(r['km'])} km  {r['title'][:50]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
