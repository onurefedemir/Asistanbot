from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import config
from .models import Listing, Search

SCHEMA = """
CREATE TABLE IF NOT EXISTS searches (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id     INTEGER NOT NULL,
    query       TEXT NOT NULL,
    min_price   INTEGER, max_price INTEGER,
    min_year    INTEGER, max_year  INTEGER,
    max_km      INTEGER,
    created_at  TEXT NOT NULL,
    last_run_at TEXT
);
CREATE TABLE IF NOT EXISTS listings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    search_id   INTEGER NOT NULL REFERENCES searches(id) ON DELETE CASCADE,
    source      TEXT NOT NULL,
    external_id TEXT NOT NULL,
    title       TEXT, url TEXT, location TEXT,
    year        INTEGER, km INTEGER,
    price       INTEGER NOT NULL,
    first_price INTEGER NOT NULL,
    min_price   INTEGER NOT NULL,
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL,
    active      INTEGER NOT NULL DEFAULT 1,
    UNIQUE (search_id, source, external_id)
);
CREATE TABLE IF NOT EXISTS price_history (
    listing_id  INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    price       INTEGER NOT NULL,
    seen_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_hist ON price_history(listing_id);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DB:
    def __init__(self, path: str | None = None) -> None:
        self.path = path or config.db_path
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self._lock = threading.RLock()  # bot (ana thread) + tarama (worker thread) aynı bağlantıyı paylaşır

    @contextmanager
    def tx(self):
        with self._lock, self.conn:
            yield self.conn

    # ---------------------------------------------------------- searches
    def add_search(self, s: Search) -> int:
        with self.tx() as c:
            cur = c.execute(
                "INSERT INTO searches (chat_id, query, min_price, max_price, min_year, max_year, max_km, created_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (s.chat_id, s.query, s.min_price, s.max_price, s.min_year, s.max_year, s.max_km, now()),
            )
            s.id = cur.lastrowid
            return s.id

    def _search(self, r: sqlite3.Row) -> Search:
        return Search(
            query=r["query"], min_price=r["min_price"], max_price=r["max_price"], min_year=r["min_year"],
            max_year=r["max_year"], max_km=r["max_km"], id=r["id"], chat_id=r["chat_id"],
        )  # fmt: skip

    def searches(self, chat_id: int | None = None) -> list[Search]:
        if chat_id is None:
            rows = self.conn.execute("SELECT * FROM searches ORDER BY id").fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM searches WHERE chat_id=? ORDER BY id", (chat_id,)).fetchall()
        return [self._search(r) for r in rows]

    def get_search(self, search_id: int, chat_id: int | None = None) -> Search | None:
        r = self.conn.execute("SELECT * FROM searches WHERE id=?", (search_id,)).fetchone()
        if not r or (chat_id is not None and r["chat_id"] != chat_id):
            return None
        return self._search(r)

    def delete_search(self, search_id: int, chat_id: int) -> bool:
        with self.tx() as c:
            return c.execute("DELETE FROM searches WHERE id=? AND chat_id=?", (search_id, chat_id)).rowcount > 0

    def is_first_run(self, search_id: int) -> bool:
        r = self.conn.execute("SELECT last_run_at FROM searches WHERE id=?", (search_id,)).fetchone()
        return r is None or r["last_run_at"] is None

    def mark_run(self, search_id: int) -> None:
        with self.tx() as c:
            c.execute("UPDATE searches SET last_run_at=? WHERE id=?", (now(), search_id))

    # ---------------------------------------------------------- listings
    def upsert_listing(self, search_id: int, l: Listing) -> tuple[str, sqlite3.Row]:
        """Döner: ('new'|'drop'|'rise'|'same', satır). Satırdaki eski fiyat 'prev_price' ile gelir."""
        ts = now()
        with self.tx() as c:
            old = c.execute(
                "SELECT * FROM listings WHERE search_id=? AND source=? AND external_id=?",
                (search_id, l.source, l.external_id),
            ).fetchone()
            if old is None:
                cur = c.execute(
                    "INSERT INTO listings (search_id, source, external_id, title, url, location, year, km,"
                    " price, first_price, min_price, first_seen, last_seen) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (search_id, l.source, l.external_id, l.title, l.url, l.location, l.year, l.km,
                     l.price, l.price, l.price, ts, ts),
                )  # fmt: skip
                lid = cur.lastrowid
                c.execute("INSERT INTO price_history VALUES (?,?,?)", (lid, l.price, ts))
                status, prev = "new", None
            else:
                lid, prev = old["id"], old["price"]
                status = "same" if l.price == prev else ("drop" if l.price < prev else "rise")
                c.execute(
                    "UPDATE listings SET title=?, url=?, location=COALESCE(?,location), year=COALESCE(?,year),"
                    " km=COALESCE(?,km), price=?, min_price=MIN(min_price,?), last_seen=?, active=1 WHERE id=?",
                    (l.title, l.url, l.location, l.year, l.km, l.price, l.price, ts, lid),
                )
                if status != "same":
                    c.execute("INSERT INTO price_history VALUES (?,?,?)", (lid, l.price, ts))
            row = c.execute("SELECT *, ? AS prev_price FROM listings WHERE id=?", (prev, lid)).fetchone()
            return status, row

    def deactivate_missing(self, search_id: int, source: str, seen_ids: set[str]) -> int:
        """Bu taramada görülmeyen ilanları pasif yap (satıldı / kaldırıldı)."""
        with self.tx() as c:
            rows = c.execute(
                "SELECT id, external_id FROM listings WHERE search_id=? AND source=? AND active=1", (search_id, source)
            ).fetchall()
            gone = [r["id"] for r in rows if r["external_id"] not in seen_ids]
            c.executemany("UPDATE listings SET active=0 WHERE id=?", [(i,) for i in gone])
            return len(gone)

    def active_listings(self, search_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM listings WHERE search_id=? AND active=1 ORDER BY price", (search_id,)
        ).fetchall()

    def get_listing(self, listing_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT l.*, s.chat_id FROM listings l JOIN searches s ON s.id=l.search_id WHERE l.id=?", (listing_id,)
        ).fetchone()

    def history(self, listing_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT price, seen_at FROM price_history WHERE listing_id=? ORDER BY seen_at", (listing_id,)
        ).fetchall()
