"""UT Bot Alerts: dönüşlerde doğru yönde sinyal, ileriye bakma yok."""

import numpy as np
import pandas as pd

from binary import utbot


def frame(close):
    return pd.DataFrame({"close": close}, index=pd.date_range("2026-01-05", periods=len(close), freq="min", tz="UTC"))


def test_signals_on_reversal():
    down = np.linspace(1.10, 1.09, 60)
    up = np.linspace(1.09, 1.11, 60)
    s = utbot.ut_bot(frame(np.r_[down, up] + np.r_[np.zeros(1), np.tile([1e-5, -1e-5], 59), [0]]), 1, 10)
    first_buy = np.flatnonzero(s == 1)
    assert len(first_buy) and first_buy[0] > 60  # yükseliş başladıktan sonra Buy
    assert not (s[:12] != 0).any()  # ısınma döneminde sinyal yok


def test_no_lookahead():
    rng = np.random.default_rng(1)
    c = 1.1 + np.cumsum(rng.normal(0, 1e-4, 500))
    a = utbot.ut_bot(frame(c), 1, 10)
    c2 = c.copy(); c2[-1] += 0.01
    b = utbot.ut_bot(frame(c2), 1, 10)
    assert (a[:-1] == b[:-1]).all()


def test_no_edge_on_random_walk():
    rng = np.random.default_rng(2)
    c = 1.1 + np.cumsum(rng.normal(0, 1e-4, 50_000))
    df = frame(c)
    r = utbot.evaluate({"X": df}, {"X": 0.85}, expiries=[1, 5], delays=(0,))
    assert r.win_rate.between(47, 53).all(), r
