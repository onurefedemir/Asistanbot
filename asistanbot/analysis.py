"""Fiyat analizi: aynı aramadaki ilanlardan yıl ve km'ye göre 'beklenen fiyat' tahmini.

Basit bir doğrusal model kullanır:  fiyat ≈ a + b*yıl + c*km
Yeterli veri yoksa (veya yıl/km eksikse) medyan fiyata düşer.
Oran = gerçek fiyat / beklenen fiyat.  0.85 → piyasanın %15 altında.
"""

from __future__ import annotations

from statistics import median
from typing import Mapping, Sequence

MIN_FOR_REGRESSION = 8


def _solve3(A: list[list[float]], b: list[float]) -> list[float] | None:
    """3x3 doğrusal sistemi Gauss eliminasyonu ile çöz."""
    M = [row[:] + [bv] for row, bv in zip(A, b)]
    n = 3
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(M[r][i]))
        if abs(M[p][i]) < 1e-12:
            return None
        M[i], M[p] = M[p], M[i]
        for r in range(n):
            if r != i:
                f = M[r][i] / M[i][i]
                for k in range(i, n + 1):
                    M[r][k] -= f * M[i][k]
    return [M[i][n] / M[i][i] for i in range(n)]


class PriceModel:
    def __init__(self, items: Sequence[Mapping]) -> None:
        prices = [it["price"] for it in items if it["price"]]
        self.median = median(prices) if prices else None
        self.coef: list[float] | None = None
        pts = [(it["year"], it["km"], it["price"]) for it in items if it["year"] and it["km"] is not None and it["price"]]
        if len(pts) >= MIN_FOR_REGRESSION and len({p[0] for p in pts}) > 1:
            # Ölçekleme: yıl-2000, km/10000 → sayısal kararlılık
            X = [(1.0, y - 2000, k / 10000) for y, k, _ in pts]
            Y = [p for *_, p in pts]
            XtX = [[sum(x[i] * x[j] for x in X) for j in range(3)] for i in range(3)]
            XtY = [sum(x[i] * y for x, y in zip(X, Y)) for i in range(3)]
            self.coef = _solve3(XtX, XtY)

    def expected(self, year: int | None, km: int | None) -> float | None:
        if self.coef and year and km is not None:
            a, b, c = self.coef
            est = a + b * (year - 2000) + c * (km / 10000)
            if est > 0:
                return est
        return self.median

    def ratio(self, item: Mapping) -> float | None:
        exp = self.expected(item["year"], item["km"])
        return item["price"] / exp if exp else None


def rank_deals(items: Sequence[Mapping], limit: int = 10) -> list[tuple[Mapping, float]]:
    """En 'fırsat' ilanları: beklenen fiyata göre en ucuzdan pahalıya."""
    model = PriceModel(items)
    scored = [(it, r) for it in items if (r := model.ratio(it)) is not None]
    scored.sort(key=lambda x: x[1])
    return scored[:limit]
