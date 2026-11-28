"""Kullanıcının Yön Okuma Testi'nde kazandığı işlemlerden çıkarılan kural (sonuçlara bakılmadan sabitlendi).

27 işlemin 16'sı doğru. Kazançların 12/16'sında karar, son 20 dakikanın yönüyle aynıydı;
kayıplarda 5/11. Yani kullanıcı trend yönünde işlem açtığında kazanmış (12/17), trende karşı
açtığında kaybetmiş (4/10). Kural ailesi:

- T1  trend: son 20 dk getirisi ≥ k × ortalama 1 dk hareket (k = 3) ve EMA10 > EMA30 → CALL (tersi → PUT).
- T2  T1 + geri çekilme: son 5 dk trendin tersine (kullanıcının "1 mum ters gelir ama sonra trend
      yönünde gider" okuması).
- T3  T1 + fiyat son 30 dk aralığının trend tarafında (CALL için üst %40, PUT için alt %40).

Vade 5 dk (testteki gibi), ayrıca 15 dk; gecikme 0 ve 1 mum. Bonferroni.
Kullanım:  python -m binary.user_trend --csv candles.csv[.gz] ...
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from . import backtest
from .tv_indicators import _score

K = 3.0


def signals(close: pd.Series) -> dict[str, np.ndarray]:
    c = close.to_numpy(float)
    mv = pd.Series(np.abs(np.diff(c, prepend=np.nan))).rolling(60).mean().to_numpy()
    ret20 = (c - np.roll(c, 20)) / mv
    ret5 = (c - np.roll(c, 5)) / mv
    ema = lambda n: close.ewm(span=n, adjust=False).mean().to_numpy()
    e = ema(10) - ema(30)
    lo, hi = close.rolling(30).min().to_numpy(), close.rolling(30).max().to_numpy()
    pos = (c - lo) / np.where(hi - lo > 0, hi - lo, np.nan)
    d = np.where((ret20 >= K) & (e > 0), 1, np.where((ret20 <= -K) & (e < 0), -1, 0))
    d[:60] = 0
    d = np.nan_to_num(d).astype(int)
    t2 = np.where(np.sign(ret5) == -d, d, 0)
    t3 = np.where(((d == 1) & (pos >= .6)) | ((d == -1) & (pos <= .4)), d, 0)
    return {"T1 trend yönünde": d, "T2 trend + geri çekilme": t2, "T3 trend + aralığın trend tarafı": t3}


def evaluate(frames, payout=0.85, expiries=(5, 15), delays=(0, 1)):
    sigs = {p: signals(df["close"]) for p, df in frames.items()}
    rows = []
    for name in next(iter(sigs.values())):
        for d in delays:
            for e in expiries:
                res = [(backtest.trades(df, sigs[p][name], e, delay=d), payout) for p, df in frames.items()]
                rows.append({"kural": name, "gecikme": d, "vade": e, **_score(res)})
    return pd.DataFrame(rows)


def load_csv(paths) -> dict[str, pd.DataFrame]:
    df = pd.concat([pd.read_csv(p) for p in paths]).drop_duplicates(["pair", "ts"])
    out = {}
    for pair, g in df.groupby("pair"):
        g = g.sort_values("ts")
        out[pair] = g.set_index(pd.to_datetime(g["ts"], unit="s", utc=True))[["open", "high", "low", "close"]]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", nargs="+", required=True)
    ap.add_argument("--payout", type=float, default=0.85)
    a = ap.parse_args()
    frames = load_csv(a.csv)
    r = evaluate(frames, a.payout)
    n = sum(len(f) for f in frames.values())
    print(f"Kullanıcı trend kuralı — {len(frames)} parite, {n} dakika, ödeme %{a.payout*100:.0f}; "
          f"{len(r)} test, Bonferroni eşiği p < {0.05 / len(r):.4f}\n")
    print(r.to_string(index=False))


if __name__ == "__main__":
    main()
