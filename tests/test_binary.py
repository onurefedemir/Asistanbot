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


def test_ml_target_and_no_lookahead():
    from binary import ml
    idx = pd.date_range("2026-01-05", periods=6, freq="min", tz="UTC")
    df = pd.DataFrame({"close": [1.0, 2.0, 1.5, 3.0, 3.0, 4.0]}, index=idx)
    # delay=1, expiry=1: hedef close[t+2] > close[t+1]
    # 1.5<2 → 0 ; 3>1.5 → 1 ; 3=3 eşit → NaN ; 4>3 → 1 ; son ikisi için gelecek yok → NaN
    np.testing.assert_array_equal(ml.target(df, 1).to_numpy(), [0, 1, np.nan, 1, np.nan, np.nan])
    # Özellikler geleceği görmemeli: son mumu değiştirmek önceki satırları etkilemez
    c = walk(300)["close"]
    f1 = ml.features(c)
    c2 = c.copy(); c2.iloc[-1] *= 1.01
    f2 = ml.features(c2)
    pd.testing.assert_frame_equal(f1.iloc[:-1], f2.iloc[:-1])


def test_ml_has_no_edge_on_random_walk():
    from binary import ml
    frames = {}
    for i, p in enumerate(["A", "B"]):
        df = walk(30 * 1440, seed=10 + i)
        frames[p] = df
    r = ml.evaluate(frames, train_days=14)
    big = r[r.trades > 300]
    assert len(big) and (big.win_rate.between(45, 55)).all(), r


def test_review_builds_prompt_and_reads_text(tmp_path, monkeypatch):
    from types import SimpleNamespace as NS
    from binary import review
    f = tmp_path / "research_delay1.txt"
    f.write_text("Testi geçen strateji: 0 / 15", encoding="utf-8")
    prompt = review.build_prompt([str(f), str(tmp_path / "yok.txt")], "Tüm sinyaller: 10 işlem", "dünkü not")
    assert "Testi geçen strateji: 0 / 15" in prompt and "dünkü not" in prompt and "yok.txt" not in prompt
    sent = {}
    def create(**kw):
        sent.update(kw)
        return NS(stop_reason="end_turn", content=[NS(type="thinking"), NS(type="text", text="Kanıt yok.")])
    client = NS(beta=NS(messages=NS(create=create)))
    assert review.review(prompt, client) == "Kanıt yok."
    assert sent["model"] == "claude-opus-5-5" and sent["fallbacks"] == "default"
    refused = NS(beta=NS(messages=NS(create=lambda **kw: NS(stop_reason="refusal", content=[]))))
    assert "üretilemedi" in review.review(prompt, refused)


def test_review_skips_without_key(monkeypatch, tmp_path):
    from binary import review
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setattr("sys.argv", ["review", "--out", str(tmp_path / "r.md")])
    assert review.main() == 0 and not (tmp_path / "r.md").exists()


def test_registry_waits_without_post_registration_data():
    from binary import registry
    cand = dict(registry.load()[0])
    assert cand["threshold"] == 0.60 and cand["expiry_bars"] == 6
    idx = pd.date_range("2026-10-01", periods=2000, freq="5min", tz="UTC")
    rng = np.random.default_rng(3)
    px = pd.DataFrame({p: 1 + np.cumsum(rng.normal(0, 1e-4, len(idx))) for p in ("EURUSD", "GBPUSD")}, index=idx)
    cand["registered_at"] = "2026-12-01"  # verinin tamamı kayıttan önce
    r = registry.validate(px, cand)
    assert r["status"].startswith("BEKLİYOR") and r["payout_85"]["trades"] == 0
