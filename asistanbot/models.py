from __future__ import annotations

import re
from dataclasses import dataclass, field

_TR = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")


def slugify(text: str) -> str:
    """'Renault Clio' -> 'renault-clio' (Türkçe karakterleri sadeleştirir)."""
    text = text.translate(_TR).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


@dataclass
class Search:
    """Kullanıcının takip ettiği arama kriterleri."""

    query: str  # "renault clio"
    min_price: int | None = None
    max_price: int | None = None
    min_year: int | None = None
    max_year: int | None = None
    max_km: int | None = None
    id: int | None = None
    chat_id: int | None = None

    @property
    def slug(self) -> str:
        return slugify(self.query)

    def matches(self, listing: "Listing") -> bool:
        """Sitenin URL filtresi çalışmasa bile sonuçları burada tekrar süzeriz."""
        p, y, k = listing.price, listing.year, listing.km
        if self.min_price and p < self.min_price:
            return False
        if self.max_price and p > self.max_price:
            return False
        if self.min_year and y and y < self.min_year:
            return False
        if self.max_year and y and y > self.max_year:
            return False
        if self.max_km and k is not None and k > self.max_km:
            return False
        # Başlıkta arama kelimelerinin geçtiğinden emin ol (reklam/alakasız ilanları ele)
        title = slugify(listing.title)
        return all(w in title for w in self.slug.split("-") if len(w) > 1)

    def describe(self) -> str:
        parts = [self.query]
        if self.min_price or self.max_price:
            parts.append(f"fiyat {_rng(self.min_price, self.max_price)} TL")
        if self.min_year or self.max_year:
            parts.append(f"yıl {_rng(self.min_year, self.max_year, sep=False)}")
        if self.max_km:
            parts.append(f"km ≤ {fmt_num(self.max_km)}")
        return ", ".join(parts)


@dataclass
class Listing:
    source: str  # "sahibinden" | "arabam"
    external_id: str
    title: str
    price: int
    url: str
    year: int | None = None
    km: int | None = None
    location: str | None = None
    extra: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.source}:{self.external_id}"


def fmt_num(n: int | float | None) -> str:
    if n is None:
        return "?"
    return f"{int(n):,}".replace(",", ".")


def _rng(lo, hi, sep: bool = True) -> str:
    f = fmt_num if sep else str
    if lo and hi:
        return f"{f(lo)}–{f(hi)}"
    if lo:
        return f"≥ {f(lo)}"
    return f"≤ {f(hi)}"
