"""Her gün yeniden eğitilen makine öğrenmesi modeli (FreqAI fikri).

Model son dakikaların hareketlerinden "giriş anından `expiry` dakika sonra fiyat yukarıda mı"
olasılığını tahmin eder. Olasılık eşiği geçerse sinyal verir (CALL veya PUT).

Değerlendirme kayan pencereyle (walk-forward) yapılır: model her gün yalnızca önceki
`train_days` günle eğitilir ve hiç görmediği ertesi günde sınanır. Böylece canlıda
yaşanacak durum taklit edilir; sonuç gerçek dışı iyimser olmaz.

Kullanım:
    python -m binary.ml evaluate     # kayan pencereli test raporu
    python -m binary.ml train        # son verilerle modeli eğitip ml_model.joblib'e kaydet
"""

from __future__ import annotations

import argparse
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from . import backtest, data
from .strategies import _rsi, _streak

EXPIRIES = [1, 2, 3, 5]
DELAY = 1  # eğitim hedefi gerçekçi gecikmeyle: sinyalden 1 dk sonra giriş
MODEL_FILE = "ml_model.joblib"
THRESHOLDS = [0.52, 0.55, 0.58, 0.60]


def features(close: pd.Series) -> pd.DataFrame:
    """Yalnızca kapanış fiyatından, t anına kadarki bilgiyle özellikler."""
    c = pd.Series(np.asarray(close, dtype=float))
    lr = np.log(c).diff()
    vol = lr.rolling(60).std()
    f = {}
    for k in (1, 2, 3, 5, 10, 15, 30):
        f[f"ret_{k}"] = (np.log(c) - np.log(c.shift(k))) / (vol * np.sqrt(k))
    for k in range(1, 6):
        f[f"lag_{k}"] = lr.shift(k) / vol
    for n in (10, 20, 50):
        f[f"z_{n}"] = (c - c.rolling(n).mean()) / c.rolling(n).std()
    f["rsi_5"] = _rsi(c, 5) / 100
    f["rsi_14"] = _rsi(c, 14) / 100
    f["streak"] = np.clip(_streak(c), -10, 10)
    f["vol_ratio"] = lr.rolling(10).std() / vol
    return pd.DataFrame(f).replace([np.inf, -np.inf], np.nan)


def target(df: pd.DataFrame, expiry: int, delay: int = DELAY) -> pd.Series:
    """1: girişten `expiry` dk sonra yukarıda, 0: aşağıda, NaN: eşit veya veri boşluğu."""
    c = df["close"].to_numpy()
    ts = df.index.as_unit("s").asi8
    span = expiry + delay
    y = np.full(len(c), np.nan)
    ok = np.zeros(len(c), bool)
    ok[:-span] = ts[span:] - ts[:-span] == span * 60
    diff = np.full(len(c), np.nan)
    diff[:-span] = c[span:] - c[delay:len(c) - expiry]
    y[ok & (diff > 0)] = 1
    y[ok & (diff < 0)] = 0
    return pd.Series(y, index=df.index)


def _model():
    return HistGradientBoostingClassifier(
        max_iter=150, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=200,
        l2_regularization=1.0, random_state=0,
    )


def _dataset(frames: dict[str, pd.DataFrame], expiry: int, start=None, end=None):
    X, y = [], []
    for df in frames.values():
        f = features(df["close"]).set_axis(df.index)
        t = target(df, expiry)
        m = f.notna().all(axis=1) & t.notna()
        if start is not None:
            m &= (df.index >= start) & (df.index < end)
        X.append(f[m])
        y.append(t[m])
    return pd.concat(X), pd.concat(y)


def signal_from_proba(p: np.ndarray, thr: float) -> np.ndarray:
    return np.where(p >= thr, 1, np.where(p <= 1 - thr, -1, 0))


def evaluate(frames: dict[str, pd.DataFrame], payout: float = 0.85, train_days: int = 14) -> pd.DataFrame:
    days = sorted({d for df in frames.values() for d in df.index.normalize().unique()})
    rows = []
    for expiry in EXPIRIES:
        res = {thr: [] for thr in THRESHOLDS}
        for i in range(train_days, len(days)):
            start, test_day = days[i - train_days], days[i]
            X, y = _dataset(frames, expiry, start, test_day)
            if len(X) < 5000:
                continue
            model = _model().fit(X, y)
            for df in frames.values():
                day = df[(df.index >= test_day) & (df.index < test_day + pd.Timedelta(days=1))]
                if len(day) < 120:
                    continue
                # Özellikler önceki 60+ dakikaya ihtiyaç duyar: günün başı için bir önceki günü de kullan
                ctx = df[(df.index >= test_day - pd.Timedelta(hours=3)) & (df.index < test_day + pd.Timedelta(days=1))]
                f = features(ctx["close"]).set_axis(ctx.index).loc[day.index]
                p = np.full(len(day), 0.5)
                ok = f.notna().all(axis=1).to_numpy()
                if ok.any():
                    p[ok] = model.predict_proba(f[ok])[:, 1]
                for thr in THRESHOLDS:
                    res[thr].append(backtest.trades(day, signal_from_proba(p, thr), expiry, delay=DELAY))
        for thr in THRESHOLDS:
            if res[thr]:
                s = backtest.stats(np.concatenate(res[thr]), payout)
                rows.append({"expiry": expiry, "threshold": thr, **s})
    return pd.DataFrame(rows)


def train(frames: dict[str, pd.DataFrame], train_days: int = 14) -> dict:
    end = max(df.index.max() for df in frames.values())
    start = end - pd.Timedelta(days=train_days)
    models = {e: _model().fit(*_dataset(frames, e, start, end + pd.Timedelta(minutes=1))) for e in EXPIRIES}
    return {"models": models, "trained_at": time.time(), "train_days": train_days}


def predict_signal(bundle: dict, close: pd.Series, expiry: int, thr: float = 0.55) -> np.ndarray:
    """paper.py için: son mumun sinyali (diğer mumlar 0)."""
    f = features(close).iloc[[-1]]
    out = np.zeros(len(close), dtype=int)
    if f.notna().all(axis=1).iloc[0]:
        p = bundle["models"][expiry].predict_proba(f)[:, 1]
        out[-1] = signal_from_proba(p, thr)[0]
    return out


def load_frames(db: str) -> dict[str, pd.DataFrame]:
    frames = {p: data.load(p, db) for p in data.PAIRS}
    return {p: df for p, df in frames.items() if len(df) > 5000}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["evaluate", "train"])
    ap.add_argument("--db", default=data.DB)
    ap.add_argument("--payout", type=float, default=0.85)
    ap.add_argument("--out", default=MODEL_FILE)
    a = ap.parse_args()
    frames = load_frames(a.db)
    if a.command == "evaluate":
        r = evaluate(frames, a.payout)
        print(f"Kayan pencereli test (14 gün eğit → ertesi gün test), giriş gecikmesi {DELAY} dk, "
              f"başa baş %{backtest.breakeven(a.payout) * 100:.2f}\n")
        print(r[["expiry", "threshold", "trades", "win_rate", "edge", "ev_per_trade", "p_value"]].to_string(index=False))
    else:
        joblib.dump(train(frames), a.out)
        print(f"Model kaydedildi: {a.out}")
