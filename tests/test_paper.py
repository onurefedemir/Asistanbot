"""Sanal işlem motoru: sinyalde işlem açar, vadede doğru sonuçla kapatır, tekrar açmaz."""

import numpy as np
import pandas as pd

from binary import paper


def quotes(now, last_price, n=120):
    # n tane kapanmış mum + içinde bulunulan dakika
    ts = [(now // 60 - n + i) * 60 for i in range(n + 1)]
    close = [1.0] * n + [last_price]
    return pd.DataFrame({"ts": ts, "open": close, "high": close, "low": close, "close": close})


def test_open_and_close(tmp_path, monkeypatch):
    clock = {"t": 1_800_000_010.0}  # dakikanın 10. saniyesi
    monkeypatch.setattr(paper.time, "time", lambda: clock["t"])
    price = {"p": 1.0}
    monkeypatch.setattr(paper, "_quotes", lambda pair, now: quotes(now, price["p"]))
    always_call = paper.Strategy("test", lambda px, pair: np.ones(len(px), dtype=int), 1)
    db = paper._db(str(tmp_path / "p.db"))

    assert paper.step(db, ["EURUSD"], [always_call], log=lambda m: None) == 0
    rows = db.execute("SELECT direction, entry_price, result FROM paper_trades").fetchall()
    assert rows == [(1, 1.0, None)]

    # Aynı dakikada tekrar çalışınca ikinci işlem açılmaz
    paper.step(db, ["EURUSD"], [always_call], log=lambda m: None)
    assert db.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0] == 1

    # Vade dolmadan kapanmaz
    clock["t"] += 30
    price["p"] = 1.5
    assert paper.step(db, ["EURUSD"], [always_call], log=lambda m: None) == 0

    # Vade doldu, fiyat yukarıda: CALL kazanır
    clock["t"] += 31
    assert paper.step(db, ["EURUSD"], [always_call], log=lambda m: None) == 1
    res = db.execute("SELECT result, pnl FROM paper_trades WHERE id=1").fetchone()
    assert res == ("win", paper.STAKE * paper.PAYOUT)
    assert "Tüm sinyaller: 1 işlem" in paper.report(db)


def test_selector_disables_losers_and_keeps_shadow(tmp_path):
    from binary import selector
    db = paper._db(str(tmp_path / "s.db"))
    rows = [("kotu", "loss")] * 60 + [("kotu", "win")] * 20 + [("iyi", "win")] * 70 + [("iyi", "loss")] * 30
    db.executemany("INSERT INTO paper_trades(strategy, pair, result) VALUES(?, 'X', ?)", rows)
    be = paper.backtest.breakeven(paper.PAYOUT)
    rng = np.random.default_rng(0)
    assert selector.status(20, 60, be, rng) == "devre dışı"
    assert selector.status(70, 30, be, rng) == "aktif"
    assert selector.status(5, 5, be, rng) == "deneme"
    assert not any(selector.choose(db, "kotu", paper.PAYOUT, rng) for _ in range(50))
    assert sum(selector.choose(db, "iyi", paper.PAYOUT, rng) for _ in range(200)) > 150
    assert selector.status(200, 100, be, rng) == "güvenilir"


def test_old_db_gets_selected_column(tmp_path):
    import sqlite3
    path = str(tmp_path / "old.db")
    old = sqlite3.connect(path)
    old.execute("CREATE TABLE paper_trades(id INTEGER PRIMARY KEY, strategy TEXT, pair TEXT, direction INTEGER,"
                " signal_ts INTEGER, entry_ts REAL, entry_price REAL, expiry INTEGER, exit_ts REAL,"
                " exit_price REAL, result TEXT, pnl REAL)")
    old.execute("INSERT INTO paper_trades(strategy, result, pnl) VALUES('a', 'win', 8.5)")
    old.commit()
    db = paper._db(path)
    assert db.execute("SELECT selected FROM paper_trades").fetchone() == (1,)
    assert "Seçicinin seçtikleri: 1" in paper.report(db)


def test_cross_pair_strategy_sees_all_pairs(tmp_path, monkeypatch):
    clock = {"t": 1_800_000_010.0}
    monkeypatch.setattr(paper.time, "time", lambda: clock["t"])
    monkeypatch.setattr(paper, "_quotes", lambda pair, now: quotes(now, 1.0))
    seen = {}
    def fn(px, pair):
        seen[pair] = list(px.columns)
        return np.zeros(len(px), dtype=int)
    db = paper._db(str(tmp_path / "c.db"))
    paper.step(db, ["EURUSD", "GBPUSD"], [paper.Strategy("x", fn, 1)], log=lambda m: None)
    assert seen == {"EURUSD": ["EURUSD", "GBPUSD"], "GBPUSD": ["EURUSD", "GBPUSD"]}


def test_default_strategies_run_on_live_shaped_data(tmp_path, monkeypatch):
    clock = {"t": 1_800_000_010.0}
    monkeypatch.setattr(paper.time, "time", lambda: clock["t"])
    rng = np.random.default_rng(0)
    def q(pair, now):
        df = quotes(now, 1.0, n=300)
        df["close"] = 1 + np.cumsum(rng.normal(0, 1e-4, len(df)))
        return df
    monkeypatch.setattr(paper, "_quotes", q)
    db = paper._db(str(tmp_path / "d.db"))
    paper.step(db, paper.data.PAIRS, paper.STRATEGIES, log=lambda m: None)  # hata vermemeli
