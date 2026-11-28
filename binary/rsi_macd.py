"""RSI + MACD dönüş stratejisi ve kullanıcının kayıp grafiklerinden çıkardığı düzeltmeler.

Temel: RSI son 5 mumda 30'un altına inmişken MACD sinyal çizgisini yukarı keserse CALL;
70'in üstüne çıkmışken aşağı keserse PUT. Giriş 1 mum sonra, vade 5 dk.

Kullanıcının düzeltmeleri (her biri sonuca bakılmadan sabitlendi, 28 Kasım 2026):
- erken: kesişim mumunda gir (gecikme 0).
- F2a: sinyal mumu "+" (doji) ve RSI hâlâ trend tarafındaysa (PUT'ta ≥ 50, CALL'da ≤ 50) girme.
- F3a: mum kırılımı şart (CALL: kapanış önceki 5 mumun en yükseğinin üstünde; PUT: en düşüğün altında).
- F3c: 60 dk trend işlemin tersineyse hem kırılım hem de "ufak olmayan" MACD düzeltmesi şart
       (MACD işlem tarafında ya da |MACD| ≤ 60 dk ortalamasının yarısı).

Eğitim dönemi Ekim–20 Kasım, ayrılmış hafta 21–27 Kasım; asıl karar 28 Kasım sonrası yeni veride:
    python -m binary.rsi_macd --candles candles --since 2026-11-29
"""

from __future__ import annotations

import argparse
import glob

import numpy as np
import pandas as pd

from . import backtest
from .user_trend import load_csv


def signals(df: pd.DataFrame) -> dict[str, np.ndarray]:
    c = df["close"]
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rsi = 100 - 100 / (1 + up / dn)
    macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    h = macd - macd.ewm(span=9, adjust=False).mean()
    xu, xd = (h > 0) & (h.shift() <= 0), (h < 0) & (h.shift() >= 0)
    base = np.where(xu & (rsi.rolling(5).min() < 30), 1, np.where(xd & (rsi.rolling(5).max() > 70), -1, 0))
    rng = (df["high"] - df["low"]).to_numpy()
    doji = (np.abs(c - df["open"]).to_numpy() <= 0.3 * rng) & (rng > 0)
    r = rsi.to_numpy()
    f2 = doji & (((base == -1) & (r >= 50)) | ((base == 1) & (r <= 50)))
    brk = ((base == 1) & (c > df["high"].shift(1).rolling(5).max()).to_numpy()) | \
          ((base == -1) & (c < df["low"].shift(1).rolling(5).min()).to_numpy())
    against = np.sign((c - c.shift(60)).to_numpy()) == -base
    small_ok = (np.abs(macd) <= 0.5 * macd.abs().rolling(60).mean()).to_numpy() | (np.sign(macd.to_numpy()) == base)
    return {"temel": base, "F2a doji+RSI → girme": np.where(f2, 0, base), "F3a mum kırılımı şart": np.where(brk, base, 0),
            "F3c ters trendde kırılım + MACD": np.where(against & ~(brk & small_ok), 0, base)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candles", default="candles")
    ap.add_argument("--since", default="2026-11-29")
    a = ap.parse_args()
    frames = load_csv(sorted(glob.glob(f"{a.candles}/*.csv.gz")))
    since = pd.Timestamp(a.since, tz="UTC")
    res: dict[str, list] = {}
    for df in frames.values():
        sig = signals(df)
        keep = df.index >= since
        for k, s in sig.items():
            for d in (1, 0):
                res.setdefault((k, d), []).append(backtest.trades(df[keep], np.asarray(s)[keep], 5, delay=d))
    print(f"RSI + MACD ve düzeltmeler — yalnızca {a.since} ve sonrası, vade 5 dk, %85 ödemede başa baş %54,05")
    for (k, d), v in res.items():
        st = backtest.stats(np.concatenate(v))
        print(f"  {k:34s} gecikme {d}: {st['trades']:5d} işlem, isabet %{st['win_rate']}, p={st['p_value']}")


if __name__ == "__main__":
    main()
