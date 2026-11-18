"""Pocket Option canlı sinyal kaydıyla (results_*.jsonl) test.

Kayıttaki her satır, Pocket'ın kendi akışından gerçek bir giriş ve çıkış fiyatı içerir.
Bu modül:
1. Kaydı strateji/parite/vade/saat bazında gerçek ödeme oranlarıyla inceler
   (çoklu test düzeltmesiyle "gizli avantajlı köşe" var mı?).
2. Giriş/çıkış fiyatlarından her parite için dakikalık Pocket fiyat serisi kurar
   (dakika başı + ~1 sn) ve bu oturumun stratejilerini — Yahoo verisinde seçilmiş,
   Pocket verisini hiç görmemiş — bu seride sınar.
3. Pocket akışında dakikalık getirilerin otokorelasyonuna bakar (Yahoo'daki
   "sahte ortalamaya dönüş" Pocket'ta da var mı?).

Kullanım:  python -m binary.pocket_log results_20261116.jsonl
"""

from __future__ import annotations

import argparse
import math

import numpy as np
import pandas as pd

from . import backtest, round2
from . import strategies as S

MIN_TRADES_CELL = 100


def load(path: str) -> pd.DataFrame:
    df = pd.read_json(path, lines=True)
    df["payout"] = df["payout_at_signal"] / 100
    df["be"] = 1 / (1 + df["payout"])
    df["win"] = (df["outcome"] == "dogru").astype(int)
    df["tie"] = (df["outcome"] == "berabere").astype(int)
    # Stake 1 birim: kazançta +ödeme, kayıpta -1, beraberlikte 0
    df["pnl"] = np.where(df.tie == 1, 0.0, np.where(df.win == 1, df["payout"], -1.0))
    return df


def _p_above(wins: int, n: int, be: float) -> float:
    if n == 0:
        return 1.0
    z = (wins - n * be - 0.5) / math.sqrt(n * be * (1 - be))
    return 0.5 * math.erfc(z / math.sqrt(2))


def breakdown(df: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    d = df[df.tie == 0]
    g = d.groupby(by).agg(trades=("win", "size"), wins=("win", "sum"), be=("be", "mean"), pnl=("pnl", "sum"))
    g = g[g.trades >= MIN_TRADES_CELL].copy()
    g["win_rate"] = (g.wins / g.trades * 100).round(2)
    g["be_pct"] = (g.be * 100).round(2)
    g["ev_per_trade"] = (g.pnl / g.trades * 100).round(2)
    g["p"] = [_p_above(int(w), int(n), b) for w, n, b in zip(g.wins, g.trades, g.be)]
    return g.sort_values("ev_per_trade", ascending=False)


def price_series(df: pd.DataFrame) -> pd.DataFrame:
    """Dakika başından ~1 sn sonraki Pocket fiyatı (sütun = parite, index = dakika)."""
    pts = pd.concat([
        df[["symbol", "entry_t", "entry_px"]].set_axis(["symbol", "t", "px"], axis=1),
        df[["symbol", "exit_t", "exit_px"]].set_axis(["symbol", "t", "px"], axis=1),
    ])
    # Çıkışlar vade sonundan ~0,3 sn önce olabilir: en yakın dakikaya yuvarla, dakika başından en çok 3 sn uzaktakiler
    minute = np.round(pts.t / 60).astype(int)
    off = pts.t - minute * 60
    pts = pts[(off > -3) & (off < 3)].assign(minute=minute)
    s = pts.groupby(["minute", "symbol"]).px.median().unstack()
    s.index = pd.to_datetime(s.index * 60, unit="s", utc=True)
    return s.asfreq("min")


def payout_by_symbol(df: pd.DataFrame) -> dict[str, float]:
    return df.groupby("symbol").payout.median().to_dict()


# Yahoo verisinde (Ekim-Kasım) seçilmiş adaylar: Pocket verisi için tamamen örneklem dışı
CANDIDATES = {
    # 1. tur: gecikmesiz girişte en güçlü görünenler (Yahoo'da sahte çıktı)
    "zscore_n10_z2.5": (lambda px, p: S.zscore_reversion(px[p], n=10, z=2.5), [1, 2, 3, 5]),
    "roc_rev_n1_z2": (lambda px, p: S.roc_reversion(px[p], n=1, z=2.0), [1, 2, 3, 5]),
    "rsi5_10_90": (lambda px, p: S.rsi_reversion(px[p], n=5, lo=10, hi=90), [1, 2, 3, 5]),
    # 2. tur: çiftler arası adaylar
    "leadlag_k2_z2.5": (lambda px, p: round2.lead_lag(px, p, k=2, z=2.5) if p in round2.SIBLINGS else None, [1, 2, 3, 5]),
    "triangle_n240_z2.5": (lambda px, p: round2.triangle(px, p, n=240, z=2.5), [1, 2, 3, 5]),
    "usdbasket_k5_z2": (lambda px, p: round2.usd_basket(px, p, k=5, z=2.0), [1, 2, 3, 5]),
}


def test_candidates(px: pd.DataFrame, payouts: dict[str, float]) -> pd.DataFrame:
    rows = []
    for name, (fn, expiries) in CANDIDATES.items():
        for delay in (0, 1):
            for e in expiries:
                res, pnl, be_w = [], 0.0, []
                for p in px.columns:
                    sig = fn(px, p)
                    if sig is None:
                        continue
                    df = px[[p]].rename(columns={p: "close"}).dropna()
                    sig = pd.Series(np.asarray(sig), index=px.index).reindex(df.index).fillna(0).to_numpy()
                    r = backtest.trades(df, sig, e, delay=delay)
                    pay = payouts.get(p, 0.85)
                    res.append(r)
                    pnl += float(((r == 1) * pay - (r == -1) * 1.0).sum())
                    be_w += [1 / (1 + pay)] * int((r != 0).sum())
                r = np.concatenate(res) if res else np.array([], dtype=np.int8)
                w, n = int((r == 1).sum()), int((r != 0).sum())
                be = float(np.mean(be_w)) if be_w else float("nan")
                rows.append({
                    "candidate": name, "delay": delay, "expiry": e, "trades": n,
                    "win_rate": round(w / n * 100, 2) if n else None, "be_pct": round(be * 100, 2) if n else None,
                    "ev_per_trade": round(pnl / n * 100, 2) if n else None,
                    "p": round(_p_above(w, n, be), 4) if n else None,
                })
    return pd.DataFrame(rows)


def autocorr(px: pd.DataFrame) -> pd.Series:
    r = np.log(px).diff()
    return r.apply(lambda c: c.autocorr(1)).round(3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    a = ap.parse_args()
    df = load(a.log)
    n_live = len(df)
    print(f"Canlı kayıt: {n_live:,} sinyal, {df.symbol.nunique()} parite, {df.strategy.nunique()} strateji, "
          f"{pd.to_datetime(df.decision_t.min(), unit='s'):%Y-%m-%d %H:%M} → {pd.to_datetime(df.exit_t.max(), unit='s'):%H:%M} UTC")
    d = df[df.tie == 0]
    print(f"Genel isabet %{d.win.mean() * 100:.2f}, ağırlıklı başa baş %{d.be.mean() * 100:.2f}, "
          f"işlem başı beklenen %{d.pnl.mean() * 100:.2f}\n")

    for by in (["strategy"], ["symbol"], ["expiry"], ["hour_utc"], ["strategy", "expiry"], ["strategy", "symbol"]):
        b = breakdown(df, by)
        alpha = 0.05 / max(len(b), 1)
        print(f"— {' × '.join(by)}: {len(b)} hücre (≥{MIN_TRADES_CELL} işlem), Bonferroni eşiği p < {alpha:.5f}, "
              f"anlamlı: {(b.p < alpha).sum()}; en iyi 5:")
        print(b.head(5)[["trades", "win_rate", "be_pct", "ev_per_trade", "p"]].to_string())
        print()

    px = price_series(df)
    print(f"Pocket fiyat serisi: {px.shape[1]} parite × {px.shape[0]} dakika "
          f"(dolu oran %{px.notna().mean().mean() * 100:.1f})")
    print("Dakikalık getirilerin 1. gecikme otokorelasyonu (Yahoo'da EURUSD -0,13, USDCAD -0,31 idi):")
    print(autocorr(px).to_string())
    print()
    t = test_candidates(px, payout_by_symbol(df))
    print("Yahoo'da seçilmiş adaylar, hiç görmedikleri Pocket verisinde (gerçek ödeme oranlarıyla):")
    print(t.to_string(index=False))
    sig = t[(t.trades >= 30) & (t.p < 0.05 / len(t))]
    print(f"\nBonferroni eşiğini (p < {0.05 / len(t):.5f}) geçen: {len(sig)}")


if __name__ == "__main__":
    main()
