"""Pocket canlı kayıt analizi: ödemeye göre başa baş, fiyat serisi kurulumu."""

import json

import numpy as np

from binary import pocket_log


def make_log(path, n=300):
    rng = np.random.default_rng(0)
    t0 = 1_794_821_760
    with open(path, "w") as f:
        for i in range(n):
            d = t0 + 60 * (i // 3)
            px = 1.1 + rng.normal(0, 1e-4)
            out = ["dogru", "yanlis", "berabere"][i % 3]
            f.write(json.dumps({
                "strategy": "s", "symbol": "EURUSD", "expiry": 60, "direction": 1, "decision_t": d,
                "hour_utc": 9, "in_session": True, "payout_at_signal": 80, "ml_prob": 0.5,
                "candles_in_history": 100, "entry_t": d + 1.1, "entry_px": px, "exit_t": d + 60.8,
                "exit_px": px, "outcome": out}) + "\n")


def test_load_breakdown_and_series(tmp_path):
    p = tmp_path / "r.jsonl"
    make_log(p)
    df = pocket_log.load(str(p))
    assert round(df.be.iloc[0], 4) == round(1 / 1.8, 4)
    assert set(df.pnl.round(2)) == {0.8, -1.0, 0.0}
    b = pocket_log.breakdown(df, ["strategy"])
    assert b.loc["s", "trades"] == 200 and b.loc["s", "win_rate"] == 50.0
    s = pocket_log.price_series(df)
    assert list(s.columns) == ["EURUSD"] and s.index.freq is not None
    assert s["EURUSD"].notna().sum() >= 99
