"""Kendini düzelten strateji seçici (Thompson örneklemeli çok kollu kumar makinesi).

Her strateji, canlı sanal işlemlerdeki kazanç/kayıplarından bir Beta dağılımı öğrenir.
- Bir strateji sinyal verdiğinde, kazanma olasılığından rastgele bir örnek çekilir;
  örnek başa baş oranının üstündeyse işlem "seçilir" (gerçekte yapılacak işlem).
  Böylece iyi gidenlere daha çok, belirsiz olanlara ara sıra, kötülere hiç işlem verilir.
- Tüm sinyaller "gölge işlem" olarak yine kaydedilir: devreden çıkarılan bir strateji
  düzelirse sistem bunu görüp onu geri alabilir.

Durumlar:
- deneme:     az veri (< MIN_TRADES), seçici keşif için ara sıra işlem verir
- aktif:      yeterli veri, başa başın üstünde olma olasılığı makul
- devre dışı: başa başın üstünde olma olasılığı < %5 (seçilmez, gölgede izlenir)
- güvenilir:  >= TRUST_TRADES işlem ve p < 0.01 (yalnızca o zaman demo hesapta denenmeli)
"""

from __future__ import annotations

import math
import sqlite3

import numpy as np

from .backtest import breakeven

PRIOR_WINS = 10   # başlangıç inancı: %50 civarı, 20 işlemlik ağırlık
PRIOR_LOSSES = 10
MIN_TRADES = 30
DISABLE_BELOW = 0.05
TRUST_TRADES = 300
TRUST_P = 0.01


def counts(db: sqlite3.Connection) -> dict[str, tuple[int, int]]:
    rows = db.execute(
        "SELECT strategy, SUM(result='win'), SUM(result='loss') FROM paper_trades "
        "WHERE result IN ('win','loss') GROUP BY strategy"
    ).fetchall()
    return {s: (int(w), int(l)) for s, w, l in rows}


def prob_above(wins: int, losses: int, be: float, rng=None, draws: int = 20_000) -> float:
    """Kazanma olasılığının başa başın üstünde olma olasılığı (Beta sonsalı, Monte Carlo)."""
    rng = rng or np.random.default_rng()
    return float((rng.beta(wins + PRIOR_WINS, losses + PRIOR_LOSSES, draws) > be).mean())


def p_value(wins: int, losses: int, be: float) -> float:
    n = wins + losses
    if not n:
        return 1.0
    z = (wins - n * be - 0.5) / math.sqrt(n * be * (1 - be))
    return 0.5 * math.erfc(z / math.sqrt(2))


def status(wins: int, losses: int, be: float, rng=None) -> str:
    n = wins + losses
    if n >= TRUST_TRADES and p_value(wins, losses, be) < TRUST_P:
        return "güvenilir"
    if n < MIN_TRADES:
        return "deneme"
    return "devre dışı" if prob_above(wins, losses, be, rng) < DISABLE_BELOW else "aktif"


def choose(db: sqlite3.Connection, strategy: str, payout: float, rng=None) -> bool:
    """Bu sinyal gerçekte işleme dönüştürülsün mü?"""
    rng = rng or np.random.default_rng()
    be = breakeven(payout)
    w, l = counts(db).get(strategy, (0, 0))
    if status(w, l, be, rng) == "devre dışı":
        return False
    return bool(rng.beta(w + PRIOR_WINS, l + PRIOR_LOSSES) > be)


def table(db: sqlite3.Connection, payout: float) -> list[dict]:
    be = breakeven(payout)
    rng = np.random.default_rng(0)
    out = []
    for s, (w, l) in sorted(counts(db).items()):
        n = w + l
        out.append({
            "strategy": s, "trades": n, "win_rate": round(w / n * 100, 1) if n else None,
            "prob_above_breakeven": round(prob_above(w, l, be, rng) * 100, 1),
            "p_value": round(p_value(w, l, be), 4), "status": status(w, l, be, rng),
        })
    return out
