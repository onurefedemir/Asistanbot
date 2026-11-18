"""Kısa vadeli ikili opsiyon sinyalleri.

Her strateji yalnızca kapanış fiyatlarını alır ve aynı uzunlukta bir dizi döndürür:
+1 = CALL (yukarı), -1 = PUT (aşağı), 0 = işlem yok.
Sinyal t anındaki kapanışa kadar olan bilgiyle hesaplanır (ileriye bakma yok).
"""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd


def _rsi(c: pd.Series, n: int) -> pd.Series:
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def rsi_reversion(c, n=7, lo=20, hi=80):
    r = _rsi(c, n)
    return np.where(r < lo, 1, np.where(r > hi, -1, 0))


def zscore_reversion(c, n=20, z=2.0):
    zs = (c - c.rolling(n).mean()) / c.rolling(n).std()
    return np.where(zs < -z, 1, np.where(zs > z, -1, 0))


def _streak(c):
    sign = np.sign(c.diff()).fillna(0).to_numpy()
    out = np.zeros(len(sign))
    for i in range(1, len(sign)):
        out[i] = out[i - 1] + sign[i] if sign[i] != 0 and np.sign(out[i - 1]) == sign[i] else sign[i]
    return out


def streak_reversion(c, m=4):
    s = _streak(c)
    return np.where(s >= m, -1, np.where(s <= -m, 1, 0))


def streak_momentum(c, m=4):
    return -streak_reversion(c, m)


def roc_momentum(c, n=5, z=2.0):
    """Son n dakikadaki getiri, oynaklığa göre z katından büyükse aynı yönde."""
    roc = c.pct_change(n)
    vol = c.pct_change().rolling(120).std() * np.sqrt(n)
    s = roc / vol
    return np.where(s > z, 1, np.where(s < -z, -1, 0))


def roc_reversion(c, n=5, z=2.0):
    return -roc_momentum(c, n, z)


def ema_trend_pullback(c, fast=9, slow=50, n=5):
    """Trend yönünde (EMA hızlı > yavaş), kısa geri çekilmede (RSI aşırı) işlem."""
    f, s = c.ewm(span=fast, adjust=False).mean(), c.ewm(span=slow, adjust=False).mean()
    r = _rsi(c, n)
    return np.where((f > s) & (r < 25), 1, np.where((f < s) & (r > 75), -1, 0))


STRATEGIES = {
    "rsi_reversion": (rsi_reversion, {"n": [3, 5, 7, 14], "lo": [10, 20, 30], "hi": [70, 80, 90]}),
    "zscore_reversion": (zscore_reversion, {"n": [10, 20, 50], "z": [1.5, 2.0, 2.5, 3.0]}),
    "streak_reversion": (streak_reversion, {"m": [3, 4, 5, 6, 7]}),
    "streak_momentum": (streak_momentum, {"m": [3, 4, 5, 6, 7]}),
    "roc_momentum": (roc_momentum, {"n": [1, 3, 5, 15], "z": [1.5, 2.0, 3.0]}),
    "roc_reversion": (roc_reversion, {"n": [1, 3, 5, 15], "z": [1.5, 2.0, 3.0]}),
    "ema_trend_pullback": (ema_trend_pullback, {"fast": [9, 21], "slow": [50, 100], "n": [3, 5]}),
}


def grid():
    """(strateji adı, fonksiyon, parametreler) üçlülerini üretir. RSI'de lo+hi=100 şartı."""
    for name, (fn, space) in STRATEGIES.items():
        keys = list(space)
        for vals in itertools.product(*space.values()):
            params = dict(zip(keys, vals))
            if name == "rsi_reversion" and params["lo"] + params["hi"] != 100:
                continue
            yield name, fn, params
