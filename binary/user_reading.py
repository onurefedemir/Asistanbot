"""Kullanıcının grafik okumasından yazılan kural v3 (28 Kasım 2026).

Kaynak: RSI MACD Çizim Masası'nda iki set (2 × 20 MACD kesişimi) üzerinde kullanıcının
kararları ve notları. Sinyal: RSI 30/70 bölgesinden gelen MACD kesişimi (mum 0); karar ve
giriş mum 0'ın kapanışında.

1) Destek/direnç fitil dönüşü (önce bakılır): son 60 mumdaki pivot diplerinden (3/3) birine
   mum 0'ın dibi değmiş (tolerans 0,5 × ortalama 1 dk hareket), kapanış seviyenin üstünde ve alt
   fitil ≥ gövde → CALL. Dirençte üst fitil ile aynısı → PUT.
2) RSI 50 sınır bölgesi (45–55):
   - RSI 50'yi MACD yönünde geçmiş → MACD yönünde.
   - RSI 45–55 arasında ve 50'yi geçmemiş → MACD'nin tersine ("50'yi kıramadı").
   - RSI 50'den uzak → MACD yönünde.

Kullanım:  python -m binary.user_reading --candles candles
"""

from __future__ import annotations

import argparse
import glob

import numpy as np
import pandas as pd

from .rsi_macd import signals
from .user_trend import load_csv

SKIP = ("EURUSD", "GBPUSD", "AUDUSD")  # Yahoo bu paritelerde yalnızca kapanış veriyor (O=H=L=C)


def _pivots(x: np.ndarray, k: int = 3):
    lo, hi = [], []
    for i in range(k, len(x) - k):
        w = x[i - k:i + k + 1]
        if x[i] == w.min():
            lo.append(i)
        if x[i] == w.max():
            hi.append(i)
    return lo, hi


def decide(o, h, l, c, rsi, side: int, sig: int = 60) -> tuple[str, str]:
    tol = 0.5 * np.mean(np.abs(np.diff(c[:sig + 1])))
    lo_i, _ = _pivots(l[:sig - 2])
    _, hi_i = _pivots(h[:sig - 2])
    body = abs(c[sig] - o[sig])
    lw, uw = min(o[sig], c[sig]) - l[sig], h[sig] - max(o[sig], c[sig])
    for j in lo_i[-6:]:
        if abs(l[sig] - l[j]) <= tol and c[sig] > l[j] and lw >= max(body, 1e-12):
            return "CALL", "destekten alt fitille döndü"
    for j in hi_i[-6:]:
        if abs(h[sig] - h[j]) <= tol and c[sig] < h[j] and uw >= max(body, 1e-12):
            return "PUT", "dirençten üst fitille döndü"
    r0, rp = rsi[sig], rsi[sig - 2]
    with_macd, against = ("CALL", "PUT") if side > 0 else ("PUT", "CALL")
    crossed = (r0 > 55 or rp < 50 < r0) if side > 0 else (r0 < 45 or rp > 50 > r0)
    if crossed:
        return with_macd, "RSI 50'yi MACD yönünde geçti"
    if 45 <= r0 <= 55:
        return against, "RSI 50 sınırında, geçemedi"
    return with_macd, "RSI 50'den uzak"


def evaluate(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for p, df in frames.items():
        if p in SKIP:
            continue
        c = df["close"]
        d = c.diff()
        up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
        dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
        rsi = (100 - 100 / (1 + up / dn)).to_numpy()
        s = np.asarray(signals(df)["temel"])
        ts = df.index.as_unit("s").asi8
        O, H, L, C = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
        for i in np.flatnonzero(s):
            if not (70 <= i < len(df) - 6 and ts[i + 5] - ts[i - 60] == 65 * 60):
                continue
            w = slice(i - 60, i + 1)
            k, why = decide(O[w], H[w], L[w], C[w], rsi[w], int(s[i]))
            sgn = 1 if k == "CALL" else -1
            rows.append({"pair": p, "ts": df.index[i], "karar": k, "neden": why,
                         **{f"r{hh}": np.sign((C[i + hh] - C[i]) * sgn) for hh in (1, 3, 5)}})
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candles", default="candles")
    a = ap.parse_args()
    r = evaluate(load_csv(sorted(glob.glob(f"{a.candles}/*.csv.gz"))))
    pct = lambda x: f"%{(x > 0).sum() / max(1, (x != 0).sum()) * 100:.1f} ({int((x != 0).sum())})"
    print(f"Kural v3 — {len(r)} sinyal; giriş sinyal mumunun kapanışında, doğru yön oranı")
    print("  tümü:", ", ".join(f"{h} mum {pct(r[f'r{h}'])}" for h in (1, 3, 5)))
    for why, g in r.groupby("neden"):
        print(f"  {why}: {len(g)} sinyal, 3 mum {pct(g.r3)}")


if __name__ == "__main__":
    main()
