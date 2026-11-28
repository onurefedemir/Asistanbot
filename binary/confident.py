"""Yalnızca "emin olunan" işlemler: model çok güvenliyse işlem aç, değilse girme.

Kullanıcının hedefi: 100 işlemde 80 doğru; tehlikeli görünen işlemlere girmemek.
Kural (28 Kasım 2026'da sabitlendi, ön kayıt):
- Her gün, o günden önceki 30 günle bir model eğitilir (gradyan artırmalı ağaçlar).
- Özellikler: 1–60 dk getiriler, 10/30/60 dk aralıktaki konum, EMA10–EMA30, oynaklık oranı,
  son mum gövdesi, saat, parite. Hedef: 1 dk sonra girilen 5 dk'lık işlem yukarıda mı kapanır.
- Yalnızca model olasılığı ≥ %74 (CALL) veya ≤ %26 (PUT) olduğunda işlem; aynı paritede
  açık işlem varken yenisi açılmaz.
- İleri doğrulama yalnızca kayıt gününden SONRAKİ günlerde yapılır. Kararı en az 100 işlem verir.

Kullanım:
    python -m binary.confident --candles candles            # ileri doğrulama (kayıt sonrası)
    python -m binary.confident --candles candles --history  # geçmiş günlerde aynı yöntem
"""

from __future__ import annotations

import argparse
import glob
import math

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from .user_trend import load_csv

REGISTERED = "2026-11-28"
CONF = 0.24          # |olasılık − 0,5| ≥ 0,24  →  olasılık ≥ %74 ya da ≤ %26
TRAIN_DAYS = 30
EXPIRY, DELAY = 5, 1
MIN_TRADES = 100
TARGET = 0.80
BE85 = 1 / 1.85


def features(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    parts = []
    for k, (p, df) in enumerate(sorted(frames.items())):
        c = df["close"]
        mv = c.diff().abs().rolling(60).mean()
        f = pd.DataFrame(index=df.index)
        for n in (1, 2, 3, 5, 10, 20, 30, 60):
            f[f"r{n}"] = (c - c.shift(n)) / mv
        for n in (10, 30, 60):
            lo, hi = c.rolling(n).min(), c.rolling(n).max()
            f[f"pos{n}"] = (c - lo) / (hi - lo)
        f["ema"] = (c.ewm(span=10).mean() - c.ewm(span=30).mean()) / mv
        f["vol"] = mv / mv.rolling(1440, min_periods=240).mean()
        f["body"] = (c - df["open"]) / mv
        f["hour"] = df.index.hour
        f["pair"] = k
        span = EXPIRY + DELAY
        ok = (df.index.to_series().shift(-span) - df.index.to_series()).dt.total_seconds() == span * 60
        f["y"] = np.where(ok, np.sign(c.shift(-span) - c.shift(-DELAY)), np.nan)
        parts.append(f)
    d = pd.concat(parts).replace([np.inf, -np.inf], np.nan)
    return d.dropna(subset=[x for x in d.columns if x != "y"])


def run_days(d: pd.DataFrame, days: list[pd.Timestamp]) -> pd.DataFrame:
    X = d.drop(columns="y")
    out = []
    for day in days:
        lo = day - pd.Timedelta(days=TRAIN_DAYS)
        cut = day - pd.Timedelta(minutes=EXPIRY + DELAY)  # sızıntı yok: etiketi güne taşan satırlar eğitime girmez
        tr = (d.index >= lo) & (d.index < cut) & d.y.notna() & (d.y != 0)
        te = (d.index >= day) & (d.index < day + pd.Timedelta(days=1))
        if tr.sum() < 20000 or te.sum() == 0:
            continue
        m = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=31, random_state=0)
        m.fit(X[tr], (d.y[tr] > 0).astype(int))
        pr = m.predict_proba(X[te])[:, 1]
        sel = np.abs(pr - 0.5) >= CONF
        if not sel.any():
            continue
        sub = d[te][sel].assign(prob=pr[sel])
        busy = {}
        for t, row in sub.sort_index().iterrows():
            if pd.isna(row.y) or t < busy.get(row.pair, t):
                continue
            busy[row.pair] = t + pd.Timedelta(minutes=EXPIRY + DELAY)
            side = 1 if row.prob > 0.5 else -1
            out.append({"ts": t, "pair": int(row.pair), "side": side, "prob": row.prob, "res": int(np.sign(side * row.y))})
    return pd.DataFrame(out)


def summary(r: pd.DataFrame, title: str) -> str:
    lines = [title]
    if r.empty:
        return "\n".join(lines + ["  Henüz işlem yok (model yeterince emin olmadı)."])
    n = int((r.res != 0).sum())
    w = int((r.res == 1).sum())
    z = (w - n * BE85 - 0.5) / math.sqrt(n * BE85 * (1 - BE85)) if n else float("nan")
    p = 0.5 * math.erfc(z / math.sqrt(2)) if n else float("nan")
    wr = w / n if n else float("nan")
    if n < MIN_TRADES:
        st = f"BEKLİYOR ({n}/{MIN_TRADES} işlem)"
    elif wr >= TARGET:
        st = "HEDEF TUTTU (≥%80)"
    elif p < 0.01:
        st = "KÂRLI AMA HEDEFİN ALTINDA"
    else:
        st = "KALDI"
    lines.append(f"  {n} işlem, {w} doğru → isabet %{wr * 100:.1f}  (hedef %80, %85 ödemede başa baş %{BE85 * 100:.2f}, p={p:.4f})  →  {st}")
    lines.append(f"  {r.ts.dt.date.nunique()} gün, günde ortalama {n / max(1, r.ts.dt.date.nunique()):.1f} işlem")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candles", default="candles")
    ap.add_argument("--history", action="store_true")
    a = ap.parse_args()
    frames = load_csv(sorted(glob.glob(f"{a.candles}/*.csv.gz")))
    d = features(frames)
    all_days = sorted(d.index.normalize().unique())
    reg = pd.Timestamp(REGISTERED, tz="UTC")
    if a.history:
        days = [x for x in all_days if x <= reg]
        print(summary(run_days(d, days), f"Emin olunan işlemler — geçmiş günler (her gün önceki {TRAIN_DAYS} günle eğitim)"))
    else:
        days = [x for x in all_days if x > reg]
        print(summary(run_days(d, days), f"Emin olunan işlemler — ileri doğrulama (kayıt {REGISTERED}, yalnızca sonraki günler)"))


if __name__ == "__main__":
    main()
