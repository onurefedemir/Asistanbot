"""TradingView göstergeleri: ileriye bakma yok, rastgele yürüyüşte avantaj yok."""

import numpy as np
import pandas as pd
import pytest

from binary import tv_indicators as T


def series(n, seed):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-01-05", periods=n, freq="min", tz="UTC")
    return pd.Series(1.1 + np.cumsum(rng.normal(0, 1e-4, n)), index=idx)


@pytest.mark.parametrize("name", list(T.INDICATORS))
def test_no_lookahead(name):
    c = series(1500, 1)
    a = np.asarray(T.INDICATORS[name](c))
    c2 = c.copy(); c2.iloc[-1] += 0.01
    b = np.asarray(T.INDICATORS[name](c2))
    assert (a[:-1] == b[:-1]).all()


def test_no_edge_on_random_walk():
    c = series(40_000, 2)
    frames = {"X": pd.DataFrame({"close": c})}
    r = T.evaluate(frames, {"X": 0.85}, expiries=[5], delays=(1,), with_vol_filter=False)
    r = r[r.trades >= 300]
    assert len(r) and r.win_rate.between(45, 55).all(), r
