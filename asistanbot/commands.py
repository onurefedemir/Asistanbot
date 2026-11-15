"""'/takip renault clio fiyat=400bin-900bin yil=2018- km=150000' metnini Search'e çevirir."""

from __future__ import annotations

import re

from .models import Search

USAGE = (
    "Kullanım:\n"
    "<code>/takip marka model [fiyat=MIN-MAX] [yil=MIN-MAX] [km=MAX]</code>\n\n"
    "Örnekler:\n"
    "<code>/takip renault clio fiyat=-900bin yil=2018- km=120000</code>\n"
    "<code>/takip volkswagen passat fiyat=1m-1.6m yil=2016-2020</code>\n"
    "<code>/takip fiat egea</code>"
)

_KEYS = {"fiyat": "price", "price": "price", "yil": "year", "yıl": "year", "year": "year", "km": "km"}


class ParseError(ValueError):
    pass


def parse_amount(raw: str) -> int | None:
    """'900bin' → 900000, '1.2m' / '1,2milyon' → 1200000, '850.000' → 850000."""
    raw = raw.strip().lower().replace("tl", "")
    if not raw:
        return None
    mult = 1
    for suf, m in (("milyon", 1_000_000), ("m", 1_000_000), ("bin", 1_000), ("k", 1_000)):
        if raw.endswith(suf):
            raw, mult = raw[: -len(suf)], m
            break
    if mult > 1:
        num = float(raw.replace(",", "."))
    else:
        num = float(raw.replace(".", "").replace(",", ""))
    if num < 0:
        raise ParseError(raw)
    return int(num * mult)


def _range(val: str) -> tuple[int | None, int | None, bool]:
    """Döner (min, max, tek_deger_mi)."""
    if "-" in val:
        lo, hi = val.split("-", 1)
        return parse_amount(lo), parse_amount(hi), False
    v = parse_amount(val)
    return v, v, True


def parse_takip(args: list[str]) -> Search:
    words: list[str] = []
    s = Search(query="")
    for tok in args:
        m = re.fullmatch(r"([a-zıA-Z]+)[=:](.+)", tok)
        if not m or m.group(1).lower() not in _KEYS:
            words.append(tok)
            continue
        key = _KEYS[m.group(1).lower()]
        try:
            lo, hi, single = _range(m.group(2))
        except ValueError as e:
            raise ParseError(f"Geçersiz değer: {tok}") from e
        if key == "price":
            s.min_price, s.max_price = (None, hi) if single else (lo, hi)
        elif key == "year":
            s.min_year, s.max_year = (lo, None) if single else (lo, hi)
        else:
            s.max_km = hi
    s.query = " ".join(words).strip()
    if not s.query:
        raise ParseError("Marka/model yazmalısınız.")
    if s.min_price and s.max_price and s.min_price > s.max_price:
        raise ParseError("Minimum fiyat maksimumdan büyük olamaz.")
    return s
