"""Ağ gerektirmeyen testler: sentetik fiyat verisiyle indikatör, backtest, portföy ve ajan döngüsü."""

import json
from types import SimpleNamespace as NS

import numpy as np
import pandas as pd
import pytest

from finance import backtest, indicators, tools
from finance.agent import FinanceAgent
from finance.portfolio import DEFAULT_CASH, Portfolio


def synthetic(n=600, seed=0):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.02, n)))
    high = close * (1 + rng.uniform(0, 0.01, n))
    low = close * (1 - rng.uniform(0, 0.01, n))
    idx = pd.date_range("2023-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame({"open": close, "high": high, "low": low, "close": close, "volume": 1.0}, index=idx)


def test_rsi_bounds():
    r = indicators.rsi(synthetic()["close"])
    assert r.between(0, 100).all()


def test_analyze_fields():
    a = indicators.analyze(synthetic())
    assert -5 <= a["score"] <= 5
    assert a["suggested_stop_loss"] < a["price"] < a["suggested_take_profit"]


@pytest.mark.parametrize("strategy", list(backtest.STRATEGIES))
def test_backtest_runs(strategy):
    r = backtest.run(synthetic(), strategy)
    assert r["trades"] >= 0
    if r["trades"]:
        assert 0 <= r["win_rate_pct"] <= 100


def test_portfolio_roundtrip(tmp_path):
    pf = Portfolio(str(tmp_path / "t.db"))
    pf.buy(1, "BTCUSDT", 100.0, 10_000)
    t = pf.sell(1, "BTCUSDT", 110.0)
    assert t["realized_pnl"] > 0
    s = pf.summary(1)
    assert s["positions"] == [] and s["closed_trades"] == 1 and s["win_rate_pct"] == 100.0
    assert s["cash"] > DEFAULT_CASH
    with pytest.raises(ValueError):
        pf.buy(1, "BTCUSDT", 100.0, 10 * DEFAULT_CASH)


def test_tool_errors_are_returned_as_text(tmp_path):
    pf = Portfolio(str(tmp_path / "t.db"))
    out = json.loads(tools.run_tool("paper_sell", {"symbol": "XYZUSDT", "reason": "t"}, 1, pf))
    assert "error" in out


def test_agent_loop_executes_custom_tools(tmp_path, monkeypatch):
    """Sahte bir oturum akışıyla ajan döngüsünün araç çalıştırıp yanıt topladığını doğrular."""
    pf = Portfolio(str(tmp_path / "t.db"))
    monkeypatch.setenv("FINANCE_AGENT_ID", "agent_x")
    monkeypatch.setenv("FINANCE_ENVIRONMENT_ID", "env_x")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    agent = FinanceAgent(pf)
    sent = []

    events = [
        NS(type="agent.custom_tool_use", id="sevt_1", name="get_portfolio", input={}),
        NS(type="session.status_idle", stop_reason=NS(type="requires_action")),
        NS(type="agent.message", content=[NS(type="text", text="Portföyünüz boş.")]),
        NS(type="session.status_idle", stop_reason=NS(type="end_turn")),
    ]

    class Stream:
        def __enter__(self): return iter(events)
        def __exit__(self, *a): return False

    fake = NS(
        beta=NS(sessions=NS(
            create=lambda **kw: NS(id="sesn_1"),
            events=NS(stream=lambda **kw: Stream(), send=lambda **kw: sent.append(kw)),
        ))
    )
    agent.client = fake
    assert agent.ask(42, "portföyüm?") == "Portföyünüz boş."
    assert sent[0]["events"][0]["type"] == "user.message"
    result = sent[1]["events"][0]
    assert result["type"] == "user.custom_tool_result" and result["custom_tool_use_id"] == "sevt_1"
    assert json.loads(result["content"][0]["text"])["cash"] == DEFAULT_CASH
    assert pf.get_session(42) == "sesn_1"
