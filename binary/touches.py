"""Kullanıcının grafik okuma yöntemi: destek/direnç dokunuş sayısı.

Kullanıcının çizimlerinden çıkarılan kurallar (sonuca bakmadan önce sabitlendi):
- R3 (3. dokunuşta dönüş): Bir direnç seviyesine 3. kez dokunulduğunda fiyat geri döner → PUT
  (destekte → CALL).
- R5 (5+ dokunuşta kırılım): Seviye 5. veya daha fazla kez test edildiğinde kırılır → dirençte CALL,
  destekte PUT.

Seviye: son `lookback` mumdaki pivot tepeleri (direnç) / dipleri (destek); birbirine `tol` kadar yakın
pivotlar aynı seviye sayılır. Dokunuş: kapanış seviyeye `tol` kadar yaklaştı ve seviyeyi kırmadı.
tol = 0,5 × ortalama 1 dk hareket (kapanıştan kapanışa, 60 mum).

Kullanım:  python -m binary.touches --pickle yahoo_frames.pkl   [--pocket results_*.jsonl]
"""

from __future__ import annotations

import argparse
import pickle

import numpy as np
import pandas as pd

from . import backtest
from .tv_indicators import _pivots, _score


def touch_signals(close: pd.Series, lookback: int = 60, piv: int = 3, tol_k: float = 0.5,
                  min_gap: int = 3) -> dict[str, np.ndarray]:
    c = close.to_numpy(float)
    n = len(c)
    ph, pl = _pivots(c, piv, piv)
    move = pd.Series(np.abs(np.diff(c, prepend=np.nan))).rolling(60).mean().to_numpy()
    r3 = np.zeros(n, int)
    r5 = np.zeros(n, int)
    ph_idx = np.flatnonzero(~np.isnan(ph))
    pl_idx = np.flatnonzero(~np.isnan(pl))
    for i in range(lookback + piv, n):
        tol = tol_k * move[i]
        if not tol or np.isnan(tol):
            continue
        for kind, idx, arr in (("res", ph_idx, ph), ("sup", pl_idx, pl)):
            # pivotlar teyit edildiği mumda (i - piv'den önce oluşmuş) biliniyor
            recent = idx[(idx > i - lookback) & (idx <= i - min_gap)]
            if len(recent) == 0:
                continue
            lv = arr[recent]
            # en çok pivot içeren seviye (tol içinde)
            counts = np.array([(np.abs(lv - x) <= tol).sum() for x in lv])
            j = counts.argmax()
            level, prior = lv[np.abs(lv - lv[j]) <= tol].mean(), counts[j]
            near = abs(c[i] - level) <= tol
            unbroken = c[i] <= level + tol if kind == "res" else c[i] >= level - tol
            if not (near and unbroken):
                continue
            touch_no = prior + 1  # bu dokunuş kaçıncı
            if touch_no == 3:
                r3[i] = -1 if kind == "res" else 1
            elif touch_no >= 5:
                r5[i] = 1 if kind == "res" else -1
    return {"R3: 3. dokunuşta dönüş": r3, "R5: 5+ dokunuşta kırılım": r5}


def evaluate(frames: dict[str, pd.DataFrame], payouts: dict[str, float], expiries=(1, 5, 15), delays=(0, 1)) -> pd.DataFrame:
    sigs = {p: touch_signals(df["close"]) for p, df in frames.items()}
    rows = []
    for name in next(iter(sigs.values())):
        for d in delays:
            for e in expiries:
                res = [(backtest.trades(df, sigs[p][name], e, delay=d), payouts.get(p, 0.85)) for p, df in frames.items()]
                rows.append({"kural": name, "gecikme": d, "vade": e, **_score(res)})
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
    print(f"Dokunuş sayısı kuralları — {src}; Bonferroni eşiği p < {0.05 / len(r):.4f}\n")
    print(r.to_string(index=False))


if __name__ == "__main__":
    main()
