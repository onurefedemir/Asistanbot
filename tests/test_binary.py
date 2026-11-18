"""İkili opsiyon backtest'inin doğruluğu: rastgele yürüyüşte avantaj görünmemeli,
gecikme ve vade doğru uygulanmalı."""

import numpy as np
import pandas as pd

from binary import backtest
from binary import strategies as S


def walk(n=50_000, seed=1):
    rng = np.random.default_rng(seed)
    c = 1.1 + np.cumsum(rng.normal(0, 1e-4, n))
    idx = pd.date_range("2026-01-05", periods=n, freq="min", tz="UTC")
    return pd.DataFrame({"open": c, "high": c, "low": c, "close": c}, index=idx)


def test_breakeven():
    assert round(backtest.breakeven(0.85), 4) == 0.5405


def test_no_edge_on_random_walk():
    df = walk()
    for name, fn, params in S.grid():
        sig = np.asarray(fn(df["close"], **params))
        s = backtest.stats(backtest.trades(df, sig, 1), 0.85)
        if s["trades"] > 500:
            assert 45 < s["win_rate"] < 55, (name, params, s)


def test_expiry_and_delay_use_correct_prices():
    idx = pd.date_range("2026-01-05", periods=6, freq="min", tz="UTC")
    c = [1.0, 2.0, 1.5, 3.0, 0.5, 4.0]
    df = pd.DataFrame({"close": c}, index=idx)
    sig = np.array([1, 0, 0, 0, 0, 0])
    assert backtest.trades(df, sig, 1).tolist() == [1]            # 2.0 > 1.0
    assert backtest.trades(df, sig, 1, delay=1).tolist() == [-1]  # 1.5 < 2.0
    assert backtest.trades(df, sig, 3, delay=1).tolist() == [-1]  # 0.5 < 2.0


def test_skips_gaps_and_overlaps():
    idx = pd.DatetimeIndex(["2026-01-05 10:00", "2026-01-05 10:01", "2026-01-05 12:00", "2026-01-05 12:01"], tz="UTC")
    df = pd.DataFrame({"close": [1.0, 2.0, 3.0, 4.0]}, index=idx)
    # 10:01 -> 12:00 arasında boşluk var: o sinyal atlanır
    assert len(backtest.trades(df, np.array([1, 1, 1, 0]), 1)) == 2
