"""3. tur: 2. turdaki en umut verici (ama tek başına yetersiz) çiftler arası sinyalleri,
tek çift özellikleriyle birlikte bir ML modeline özellik olarak verir (Qlib'in "alfa faktörü" fikri).

Değerlendirme ml.py ile aynı: 14 gün eğit → hiç görülmemiş ertesi gün test, 1 dk giriş gecikmesi.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from . import backtest, ml
from .round2 import SIBLINGS, TRIANGLES, USD_SIDE, _vol, aligned

THRESHOLDS = [0.53, 0.55, 0.57, 0.60]


def cross_features(px: pd.DataFrame, pair: str) -> pd.DataFrame:
    pf = px.ffill(limit=2)
    lp = np.log(pf)
    v = _vol(px[pair])
    f = {}
    for k in (1, 2, 3, 5, 15):
        lr = lp.diff(k)
        sib = pd.concat([s * lr[p] for p, s in SIBLINGS[pair] if p in px], axis=1).mean(axis=1)
        f[f"leadlag_{k}"] = (sib - lr[pair]) / (v * np.sqrt(k))
        if pair in USD_SIDE:
            basket = pd.concat([-s * lr[p] for p, s in USD_SIDE.items() if p in px and p != pair], axis=1).mean(axis=1)
            f[f"basket_{k}"] = (-USD_SIDE[pair] * basket - lr[pair]) / (v * np.sqrt(k))
        else:
            f[f"basket_{k}"] = 0.0  # bu çift için yok: tüm çiftlerde aynı sütunlar olsun
    for n in (20, 60, 240):
        f[f"tri_{n}"] = 0.0
    if pair in TRIANGLES:
        a, b, op = TRIANGLES[pair]
        implied = pf[a] / pf[b] if op == "div" else pf[a] * pf[b]
        dev = lp[pair] - np.log(implied)
        for n in (20, 60, 240):
            f[f"tri_{n}"] = (dev - dev.rolling(n).mean()) / dev.rolling(n).std()
    out = pd.DataFrame(f, index=px.index)
    own = ml.features(px[pair]).set_axis(px.index)
    hrs = px.index.hour
    out["hour_sin"], out["hour_cos"] = np.sin(2 * np.pi * hrs / 24), np.cos(2 * np.pi * hrs / 24)
    return pd.concat([own, out], axis=1).replace([np.inf, -np.inf], np.nan)


def evaluate(px: pd.DataFrame, payout: float = 0.85, train_days: int = 14) -> pd.DataFrame:
    feats, targets, frames = {}, {}, {}
    for pair in px.columns:
        df = px[[pair]].rename(columns={pair: "close"}).dropna()
        frames[pair] = df
        feats[pair] = cross_features(px, pair).reindex(df.index)
        targets[pair] = {e: ml.target(df, e) for e in ml.EXPIRIES}
    days = sorted(px.index.normalize().unique())
    rows = []
    for e in ml.EXPIRIES:
        res = {t: [] for t in THRESHOLDS}
        for i in range(train_days, len(days)):
            lo, day = days[i - train_days], days[i]
            nxt = day + pd.Timedelta(days=1)
            X, y = [], []
            for pair, df in frames.items():
                m = (df.index >= lo) & (df.index < day)
                f, t = feats[pair][m], targets[pair][e][m]
                ok = f.notna().all(axis=1) & t.notna()
                X.append(f[ok]); y.append(t[ok])
            X, y = pd.concat(X), pd.concat(y)
            if len(X) < 5000:
                continue
            model = ml._model().fit(X, y)
            for pair, df in frames.items():
                m = (df.index >= day) & (df.index < nxt)
                if m.sum() < 120:
                    continue
                f = feats[pair][m]
                p = np.full(m.sum(), 0.5)
                ok = f.notna().all(axis=1).to_numpy()
                if ok.any():
                    p[ok] = model.predict_proba(f[ok])[:, 1]
                for t in THRESHOLDS:
                    res[t].append(backtest.trades(df[m], ml.signal_from_proba(p, t), e, delay=ml.DELAY))
        for t in THRESHOLDS:
            if res[t]:
                rows.append({"expiry": e, "threshold": t, **backtest.stats(np.concatenate(res[t]), payout)})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="binary.db")
    ap.add_argument("--payout", type=float, default=0.85)
    a = ap.parse_args()
    r = evaluate(aligned(a.db), a.payout)
    print(f"3. tur — çiftler arası özellikli ML, kayan pencere (14 gün → ertesi gün), giriş gecikmesi 1 dk, "
          f"başa baş %{backtest.breakeven(a.payout) * 100:.2f}\n")
    print(r[["expiry", "threshold", "trades", "win_rate", "edge", "ev_per_trade", "p_value"]].to_string(index=False))
