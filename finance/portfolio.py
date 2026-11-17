"""Sanal (paper trading) portföy, SQLite'ta saklanır.

Gerçek para kullanılmaz. Her Telegram sohbeti kendi portföyüne sahiptir.
"""

from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager

DEFAULT_CASH = 100_000.0
FEE_PCT = 0.1


class Portfolio:
    def __init__(self, path: str = "finance.db"):
        self.path = path
        with self._db() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS accounts(
                    chat_id INTEGER PRIMARY KEY, cash REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS positions(
                    chat_id INTEGER, symbol TEXT, qty REAL, avg_price REAL,
                    PRIMARY KEY(chat_id, symbol));
                CREATE TABLE IF NOT EXISTS trades(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, ts REAL,
                    side TEXT, symbol TEXT, qty REAL, price REAL, fee REAL,
                    realized_pnl REAL, reason TEXT);
                CREATE TABLE IF NOT EXISTS sessions(
                    chat_id INTEGER PRIMARY KEY, session_id TEXT);
                """
            )

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path)
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def _cash(self, db, chat_id: int) -> float:
        row = db.execute("SELECT cash FROM accounts WHERE chat_id=?", (chat_id,)).fetchone()
        if row is None:
            db.execute("INSERT INTO accounts VALUES(?,?)", (chat_id, DEFAULT_CASH))
            return DEFAULT_CASH
        return row[0]

    def buy(self, chat_id: int, symbol: str, price: float, amount: float, reason: str = "") -> dict:
        """`amount` nakit tutarıdır (ör. 5000 birim para ile al)."""
        symbol = symbol.upper()
        if amount <= 0 or price <= 0:
            raise ValueError("Tutar ve fiyat pozitif olmalı.")
        with self._db() as db:
            cash = self._cash(db, chat_id)
            if amount > cash:
                raise ValueError(f"Yetersiz bakiye: {cash:.2f}")
            fee = amount * FEE_PCT / 100
            qty = (amount - fee) / price
            row = db.execute(
                "SELECT qty, avg_price FROM positions WHERE chat_id=? AND symbol=?", (chat_id, symbol)
            ).fetchone()
            if row:
                new_qty = row[0] + qty
                avg = (row[0] * row[1] + qty * price) / new_qty
                db.execute(
                    "UPDATE positions SET qty=?, avg_price=? WHERE chat_id=? AND symbol=?",
                    (new_qty, avg, chat_id, symbol),
                )
            else:
                db.execute("INSERT INTO positions VALUES(?,?,?,?)", (chat_id, symbol, qty, price))
            db.execute("UPDATE accounts SET cash=? WHERE chat_id=?", (cash - amount, chat_id))
            db.execute(
                "INSERT INTO trades(chat_id,ts,side,symbol,qty,price,fee,realized_pnl,reason) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (chat_id, time.time(), "BUY", symbol, qty, price, fee, 0.0, reason),
            )
        return {"side": "BUY", "symbol": symbol, "qty": qty, "price": price, "fee": fee,
                "cash_left": cash - amount}

    def sell(self, chat_id: int, symbol: str, price: float, fraction: float = 1.0, reason: str = "") -> dict:
        """Pozisyonun `fraction` kadarını satar (1.0 = tamamı)."""
        symbol = symbol.upper()
        if not 0 < fraction <= 1:
            raise ValueError("fraction 0 ile 1 arasında olmalı.")
        with self._db() as db:
            cash = self._cash(db, chat_id)
            row = db.execute(
                "SELECT qty, avg_price FROM positions WHERE chat_id=? AND symbol=?", (chat_id, symbol)
            ).fetchone()
            if not row or row[0] <= 0:
                raise ValueError(f"{symbol} pozisyonu yok.")
            qty = row[0] * fraction
            gross = qty * price
            fee = gross * FEE_PCT / 100
            pnl = gross - fee - qty * row[1]
            remaining = row[0] - qty
            if remaining <= 1e-12:
                db.execute("DELETE FROM positions WHERE chat_id=? AND symbol=?", (chat_id, symbol))
            else:
                db.execute(
                    "UPDATE positions SET qty=? WHERE chat_id=? AND symbol=?", (remaining, chat_id, symbol)
                )
            db.execute("UPDATE accounts SET cash=? WHERE chat_id=?", (cash + gross - fee, chat_id))
            db.execute(
                "INSERT INTO trades(chat_id,ts,side,symbol,qty,price,fee,realized_pnl,reason) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (chat_id, time.time(), "SELL", symbol, qty, price, fee, pnl, reason),
            )
        return {"side": "SELL", "symbol": symbol, "qty": qty, "price": price, "fee": fee,
                "realized_pnl": pnl, "cash": cash + gross - fee}

    def summary(self, chat_id: int, prices: dict[str, float] | None = None) -> dict:
        prices = prices or {}
        with self._db() as db:
            cash = self._cash(db, chat_id)
            rows = db.execute(
                "SELECT symbol, qty, avg_price FROM positions WHERE chat_id=?", (chat_id,)
            ).fetchall()
            realized = db.execute(
                "SELECT COALESCE(SUM(realized_pnl),0), COUNT(*), "
                "COALESCE(SUM(CASE WHEN realized_pnl>0 THEN 1 ELSE 0 END),0) "
                "FROM trades WHERE chat_id=? AND side='SELL'",
                (chat_id,),
            ).fetchone()
        positions = []
        value = cash
        for sym, qty, avg in rows:
            px = prices.get(sym, avg)
            positions.append({
                "symbol": sym, "qty": qty, "avg_price": avg, "price": px,
                "value": qty * px, "unrealized_pnl_pct": round((px / avg - 1) * 100, 2),
            })
            value += qty * px
        closed = realized[1]
        return {
            "cash": round(cash, 2),
            "positions": positions,
            "total_value": round(value, 2),
            "total_return_pct": round((value / DEFAULT_CASH - 1) * 100, 2),
            "realized_pnl": round(realized[0], 2),
            "closed_trades": closed,
            "win_rate_pct": round(realized[2] / closed * 100, 1) if closed else None,
        }

    def history(self, chat_id: int, limit: int = 20) -> list[dict]:
        with self._db() as db:
            rows = db.execute(
                "SELECT ts, side, symbol, qty, price, realized_pnl, reason FROM trades "
                "WHERE chat_id=? ORDER BY id DESC LIMIT ?",
                (chat_id, limit),
            ).fetchall()
        return [
            {"time": time.strftime("%Y-%m-%d %H:%M", time.localtime(r[0])), "side": r[1],
             "symbol": r[2], "qty": r[3], "price": r[4], "realized_pnl": r[5], "reason": r[6]}
            for r in rows
        ]

    def reset(self, chat_id: int) -> None:
        with self._db() as db:
            for t in ("accounts", "positions", "trades"):
                db.execute(f"DELETE FROM {t} WHERE chat_id=?", (chat_id,))

    # Claude oturum kimliği (sohbet başına bir Managed Agents oturumu)
    def get_session(self, chat_id: int) -> str | None:
        with self._db() as db:
            row = db.execute("SELECT session_id FROM sessions WHERE chat_id=?", (chat_id,)).fetchone()
        return row[0] if row else None

    def set_session(self, chat_id: int, session_id: str | None) -> None:
        with self._db() as db:
            if session_id is None:
                db.execute("DELETE FROM sessions WHERE chat_id=?", (chat_id,))
            else:
                db.execute("INSERT OR REPLACE INTO sessions VALUES(?,?)", (chat_id, session_id))
