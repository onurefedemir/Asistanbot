"""Kullanıcının "teyitli kırılım" okuması — otomatik versiyon (sonuçlara bakılmadan önce sabitlendi).

Kullanıcının 30 grafiklik testinde "fiyat çizgiyi geçmiş ve üstünde duruyor" gerekçeli kararları 4/4,
genel "kırılım olmuş" gerekçeli kararları 0/3 tuttu. Kural:

- Çizgiler (son 60 mum, yalnızca o ana kadar teyit edilmiş pivotlarla, pivot 3/3):
  * yatay: en çok dokunulan direnç (pivot tepeleri) ve destek (pivot dipleri) seviyesi, en az 2 dokunuş;
  * trend: son iki pivot tepesinden geçen çizgi (direnç) ve son iki pivot dibinden geçen çizgi (destek).
- Kırılım: kapanış dirençin üstüne (destekte altına) geçer.
- Teyit: kırılımdan sonraki `confirm` mumun hepsi de çizginin ötesinde kapanır → kırılım yönünde sinyal
  (yukarı → CALL, aşağı → PUT). Her kırılım için tek sinyal.

Kullanım:  python -m binary.breakout_confirm --pickle yahoo_frames.pkl  [--pocket results_*.jsonl]
"""

from __future__ import annotations

import argparse
import pickle

import numpy as np
import pandas as pd

from . import backtest
from .tv_indicators import _pivots, _score

PIV, LOOKBACK = 3, 60


def _lines(c: np.ndarray, kind: str):
    """Her mum için (direnç, destek) çizgi değeri; o ana kadar bilinen pivotlarla. NaN = çizgi yok."""
    n = len(c)
    ph, pl = _pivots(c, PIV, PIV)
    move = pd.Series(np.abs(np.diff(c, prepend=np.nan))).rolling(60).mean().to_numpy()
    res = np.full(n, np.nan)
    sup = np.full(n, np.nan)
    hi_idx, lo_idx = [], []  # (pivot mumu, değer)
    for i in range(n):
        if not np.isnan(ph[i]):
            hi_idx.append((i - PIV, ph[i]))
        if not np.isnan(pl[i]):
            lo_idx.append((i - PIV, pl[i]))
        hi = [(j, v) for j, v in hi_idx if j > i - LOOKBACK]
        lo = [(j, v) for j, v in lo_idx if j > i - LOOKBACK]
        if kind == "trend":
            if len(hi) >= 2:
                (j1, v1), (j2, v2) = hi[-2], hi[-1]
                res[i] = v2 + (v2 - v1) / (j2 - j1) * (i - j2)
            if len(lo) >= 2:
                (j1, v1), (j2, v2) = lo[-2], lo[-1]
                sup[i] = v2 + (v2 - v1) / (j2 - j1) * (i - j2)
        else:
            tol = 0.5 * move[i]
            if not tol or np.isnan(tol):
                continue
            for arr, out in ((hi, res), (lo, sup)):
                if len(arr) < 2:
                    continue
                vals = np.array([v for _, v in arr])
                cnt = np.array([(np.abs(vals - x) <= tol).sum() for x in vals])
                if cnt.max() >= 2:
                    x = vals[cnt.argmax()]
                    out[i] = vals[np.abs(vals - x) <= tol].mean()
        # hafızayı sınırla
        hi_idx = hi_idx[-20:]
        lo_idx = lo_idx[-20:]
    return res, sup


def confirmed_breakout(close: pd.Series, kind: str = "horizontal", confirm: int = 1) -> np.ndarray:
    c = close.to_numpy(float)
    res, sup = _lines(c, kind)
    n = len(c)
    sig = np.zeros(n, int)
    for i in range(confirm + 1, n):
        b = i - confirm  # kırılım mumu
        # direnç yukarı kırıldı ve sonraki confirm mum üstünde kaldı
        if not np.isnan(res[b - 1]) and c[b - 1] <= res[b - 1] and c[b] > res[b] and \
                all(not np.isnan(res[k]) and c[k] > res[k] for k in range(b + 1, i + 1)):
            sig[i] = 1
        elif not np.isnan(sup[b - 1]) and c[b - 1] >= sup[b - 1] and c[b] < sup[b] and \
                all(not np.isnan(sup[k]) and c[k] < sup[k] for k in range(b + 1, i + 1)):
            sig[i] = -1
    return sig


VARIANTS = [(k, m) for k in ("horizontal", "trend") for m in (1, 2)]


def evaluate(frames, payouts, expiries=(1, 5, 15), delays=(0, 1)):
    rows = []
    for kind, m in VARIANTS:
        sigs = {p: confirmed_breakout(df["close"], kind, m) for p, df in frames.items()}
        for d in delays:
            for e in expiries:
                res = [(backtest.trades(df, sigs[p], e, delay=d), payouts.get(p, 0.85)) for p, df in frames.items()]
                rows.append({"çizgi": "yatay" if kind == "horizontal" else "trend", "teyit": m, "gecikme": d, "vade": e, **_score(res)})
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pickle")
    ap.add_argument("--pocket")
    a = ap.parse_args()
    if a.pocket:
        from . import pocket_log
        log = pocket_log.load(a.pocket)
        px = pocket_log.price_series(log)
        frames = {p: px[[p]].rename(columns={p: "close"}).dropna() for p in px.columns}
        payouts = pocket_log.payout_by_symbol(log)
        src = "Pocket'ın kendi fiyatları, gerçek ödemeler"
    else:
        frames = pickle.load(open(a.pickle, "rb"))
        payouts = {p: 0.85 for p in frames}
        src = f"Yahoo 1 dk, {len(frames)} parite, %85 ödeme"
    r = evaluate(frames, payouts)
    print(f"Teyitli kırılım — {src}; {len(r)} test, Bonferroni eşiği p < {0.05 / len(r):.4f}\n")
    print(r.to_string(index=False))


if __name__ == "__main__":
    main()
