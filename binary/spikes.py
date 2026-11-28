"""Çok büyük 1 dakikalık mumların (sıçramaların) kaydı.

Tanım: kapanıştan kapanışa 1 dk hareketi, o paritenin son 24 saatteki tipik (medyan) 1 dk
hareketinin en az `K` katı. Ardışık olmayan dakikalar (veri boşluğu) sayılmaz.
Her sıçrama için: parite, zaman (UTC ve TSİ), büyüklük (pip ve kat), yön, sonraki 5 dk'da
geri dönüp dönmediği. EURUSD/GBPUSD/AUDUSD verisi yalnızca kapanış olduğu için ayrıca işaretlenir.

Kullanım:
    python -m binary.spikes --candles candles --out spikes.csv   # kaydı günceller (eskileri korur)
    python -m binary.spikes --candles candles --report           # özet
"""

from __future__ import annotations

import argparse
import glob
import os

import numpy as np
import pandas as pd

from .user_trend import load_csv

K = 10
CLOSE_ONLY = {"EURUSD", "GBPUSD", "AUDUSD"}


def find(frames: dict[str, pd.DataFrame], k: float = K) -> pd.DataFrame:
    rows = []
    for p, df in frames.items():
        c = df["close"]
        step = df.index.to_series().diff().dt.total_seconds().to_numpy()
        r = c.diff().where(step == 60)
        med = r.abs().rolling(1440, min_periods=300).median()
        z = r.abs() / med.replace(0, np.nan)
        pip = 0.01 if "JPY" in p else 0.0001
        cc = c.to_numpy()
        for i in np.flatnonzero((z >= k).to_numpy()):
            t = df.index[i]
            after = cc[i + 5] - cc[i] if i + 5 < len(cc) and (df.index[i + 5] - t).total_seconds() == 300 else np.nan
            mv = cc[i] - cc[i - 1]
            rows.append({"pair": p, "ts_utc": t.strftime("%Y-%m-%d %H:%M"), "tsi": (t + pd.Timedelta(hours=3)).strftime("%Y-%m-%d %H:%M"),
                         "yon": "yukari" if mv > 0 else "asagi", "pip": round(abs(mv) / pip, 1), "kat": round(float(z.iloc[i]), 1),
                         "sonraki_5dk": "" if np.isnan(after) else ("geri_dondu" if np.sign(after) == -np.sign(mv) else "devam" if np.sign(after) == np.sign(mv) else "yatay"),
                         "sadece_kapanis": p in CLOSE_ONLY})
    return pd.DataFrame(rows)


def report(s: pd.DataFrame) -> str:
    if s.empty:
        return "Kayıtlı sıçrama yok."
    s = s[~s.sadece_kapanis]
    s = s.assign(gun=s.tsi.str[:10], saat=s.tsi.str[11:13].astype(int))
    days = s.gun.nunique()
    out = [f"Çok büyük 1 dk mumlar (≥{K}× tipik hareket) — {s.gun.min()} … {s.gun.max()} (TSİ), {days} gün", ""]
    for p, g in s.groupby("pair"):
        top = g.saat.value_counts().head(3)
        out.append(f"{p}: {len(g)} sıçrama, {g.gun.nunique()} günde; ort. {g.pip.mean():.1f} pip; "
                   f"en sık saatler (TSİ) {', '.join(f'{h:02d}:00 ({n})' for h, n in top.items())}; "
                   f"5 dk içinde geri döndü %{(g.sonraki_5dk == 'geri_dondu').mean() * 100:.0f}")
    night = s[s.saat.isin([0, 1, 2])]
    out += ["", f"Gece 00–02 TSİ (gün dönümü): {len(night)}/{len(s)} sıçrama; 5 dk içinde geri dönen %{(night.sonraki_5dk == 'geri_dondu').mean() * 100:.0f}"]
    last = s[s.gun == s.gun.max()]
    out += ["", f"Son gün ({s.gun.max()}): " + ("; ".join(f"{r.pair} {r.tsi[11:]} {r.yon} {r.pip} pip" for r in last.itertuples()) or "yok")]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candles", default="candles")
    ap.add_argument("--out")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    s = find(load_csv(sorted(glob.glob(f"{a.candles}/*.csv.gz"))))
    if a.out:
        if os.path.exists(a.out):
            s = pd.concat([pd.read_csv(a.out), s]).drop_duplicates(["pair", "ts_utc"], keep="last")
        s = s.sort_values(["ts_utc", "pair"])
        s.to_csv(a.out, index=False)
        print(f"{a.out}: {len(s)} sıçrama kayıtlı")
    if a.report or not a.out:
        print(report(s))


if __name__ == "__main__":
    main()
