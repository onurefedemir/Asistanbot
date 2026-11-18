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
    always_call = paper.Strategy("test", lambda c: np.ones(len(c), dtype=int), 1)
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
    assert "Kapanan işlem: 1" in paper.report(db)
