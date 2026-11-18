"""Canlı izleyip karar veren SANAL işlem motoru (paper trading). Hiçbir platformda işlem açmaz.

Her döngüde:
1. Her çiftin son kapanmış 1 dk mumlarını alır, her stratejinin sinyalini hesaplar.
2. Sinyal varsa ve o strateji+çift için açık işlem yoksa, ANLIK fiyattan sanal işlem açar.
3. Vadesi dolan işlemleri o anki fiyatla kapatır: kazanç / kayıp / iade.

Kullanım:
    python -m binary.paper                   # sürekli çalışır (Ctrl+C ile durur)
    python -m binary.paper --max-trades 10   # 10 işlem kapanınca durur ve özet verir
    python -m binary.paper --report          # şimdiye kadarki sonuçlar
"""

from __future__ import annotations

import argparse
import sqlite3
import time
from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from . import backtest, data
from . import strategies as S

PAYOUT = 0.85
STAKE = 10.0


@dataclass
class Strategy:
    name: str
    fn: Callable[[pd.Series], np.ndarray]
    expiry: int  # dakika


# Backtest'te öne çıkan adaylar: gecikmesiz girişte güçlü görünenler + gecikmeli testte en iyi olanlar
STRATEGIES = [
    Strategy("zscore_n10_z2.5_2dk", lambda c: S.zscore_reversion(c, n=10, z=2.5), 2),
    Strategy("roc_rev_n1_z2_1dk", lambda c: S.roc_reversion(c, n=1, z=2.0), 1),
    Strategy("roc_rev_n1_z3_1dk", lambda c: S.roc_reversion(c, n=1, z=3.0), 1),
    Strategy("zscore_n20_z3_1dk", lambda c: S.zscore_reversion(c, n=20, z=3.0), 1),
    Strategy("rsi5_10_90_1dk", lambda c: S.rsi_reversion(c, n=5, lo=10, hi=90), 1),
    Strategy("streak_mom6_5dk", lambda c: S.streak_momentum(c, m=6), 5),
]


def _db(path: str) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.execute(
        """CREATE TABLE IF NOT EXISTS paper_trades(
            id INTEGER PRIMARY KEY AUTOINCREMENT, strategy TEXT, pair TEXT, direction INTEGER,
            signal_ts INTEGER, entry_ts REAL, entry_price REAL, expiry INTEGER,
            exit_ts REAL, exit_price REAL, result TEXT, pnl REAL)"""
    )
    return db


def _quotes(pair: str, now: int) -> pd.DataFrame | None:
    try:
        df = data.fetch_chunk(pair, now - 3 * 3600, now + 60)
    except Exception as e:
        print(f"  {pair}: veri alınamadı ({type(e).__name__})")
        return None
    return df if len(df) >= 60 else None


def step(db: sqlite3.Connection, pairs: list[str], strategies: list[Strategy], log=print) -> int:
    """Tek döngü. Bu döngüde kapanan işlem sayısını döndürür."""
    now = int(time.time())
    closed = 0
    open_rows = db.execute(
        "SELECT id, strategy, pair, direction, entry_ts, entry_price, expiry FROM paper_trades WHERE result IS NULL"
    ).fetchall()
    open_keys = {(r[1], r[2]) for r in open_rows}

    for pair in pairs:
        df = _quotes(pair, now)
        if df is None:
            continue
        live_price = float(df["close"].iloc[-1])  # içinde bulunulan dakikanın son fiyatı = anlık fiyat
        live_ts = int(df["ts"].iloc[-1])

        # 1) Vadesi dolan işlemleri kapat
        for tid, sname, tpair, d, entry_ts, entry_price, expiry in open_rows:
            if tpair != pair or time.time() < entry_ts + expiry * 60:
                continue
            diff = (live_price - entry_price) * d
            result = "tie" if diff == 0 else ("win" if diff > 0 else "loss")
            pnl = STAKE * PAYOUT if result == "win" else (0.0 if result == "tie" else -STAKE)
            db.execute(
                "UPDATE paper_trades SET exit_ts=?, exit_price=?, result=?, pnl=? WHERE id=?",
                (time.time(), live_price, result, pnl, tid),
            )
            open_keys.discard((sname, tpair))
            closed += 1
            mark = {"win": "✅ KAZANÇ", "loss": "❌ KAYIP", "tie": "➖ İADE"}[result]
            log(f"[{time.strftime('%H:%M:%S')}] #{tid} {mark} {tpair} {sname}: "
                f"{entry_price:.5f} → {live_price:.5f}  ({pnl:+.2f})")

        # 2) Yeni sinyaller: yalnızca kapanmış mumlarla (backtest ile aynı)
        done = df[df["ts"] <= now - 60]
        if len(done) < 60:
            continue
        signal_ts = int(done["ts"].iloc[-1])
        # Sinyal mumu kapanalı 45 sn'den fazla olduysa geç kalınmıştır
        if now - (signal_ts + 60) > 45 or live_ts <= signal_ts:
            continue
        close = done["close"].reset_index(drop=True)
        for st in strategies:
            if (st.name, pair) in open_keys:
                continue
            sig = int(np.asarray(st.fn(close))[-1])
            if not sig:
                continue
            dup = db.execute(
                "SELECT 1 FROM paper_trades WHERE strategy=? AND pair=? AND signal_ts=?", (st.name, pair, signal_ts)
            ).fetchone()
            if dup:
                continue
            cur = db.execute(
                "INSERT INTO paper_trades(strategy,pair,direction,signal_ts,entry_ts,entry_price,expiry)"
                " VALUES(?,?,?,?,?,?,?)",
                (st.name, pair, sig, signal_ts, time.time(), live_price, st.expiry),
            )
            open_keys.add((st.name, pair))
            log(f"[{time.strftime('%H:%M:%S')}] #{cur.lastrowid} AÇ {pair} {'CALL ↑' if sig > 0 else 'PUT ↓'} "
                f"{st.expiry}dk @ {live_price:.5f}  ({st.name})")
    db.commit()
    return closed


def report(db: sqlite3.Connection) -> str:
    rows = db.execute("SELECT strategy, pair, result, pnl FROM paper_trades WHERE result IS NOT NULL").fetchall()
    if not rows:
        return "Henüz kapanmış işlem yok."
    df = pd.DataFrame(rows, columns=["strategy", "pair", "result", "pnl"])
    code = df["result"].map({"win": 1, "loss": -1, "tie": 0}).to_numpy(dtype=np.int8)
    total = backtest.stats(code, PAYOUT)
    lines = [
        f"Kapanan işlem: {len(df)}  (kazanç {int((df.result == 'win').sum())}, "
        f"kayıp {int((df.result == 'loss').sum())}, iade {int((df.result == 'tie').sum())})",
        f"Kazanma oranı: %{total['win_rate']}  |  başa baş: %{total['breakeven']}",
        f"Toplam K/Z: {df.pnl.sum():+.2f} (işlem başı {STAKE:.0f} birim, ödeme %{PAYOUT*100:.0f})",
        f"Anlamlılık: p={total['p_value']} (0.01'in altı olmadıkça avantaj kanıtlanmış sayılmaz)",
        "",
        "Strateji bazında:",
    ]
    for name, g in df.groupby("strategy"):
        w, n = int((g.result == "win").sum()), int((g.result != "tie").sum())
        lines.append(f"  {name:<22} {w}/{n}  K/Z {g.pnl.sum():+.2f}")
    if len(df) < 300:
        lines += ["", f"⚠️ {len(df)} işlem istatistik için çok az; en az 300 işlem gerekir."]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Canlı sanal işlem motoru (işlem açmaz)")
    ap.add_argument("--db", default="paper.db")
    ap.add_argument("--pairs", nargs="*", default=data.PAIRS)
    ap.add_argument("--max-trades", type=int, default=0, help="Bu kadar işlem kapanınca dur (0 = sınırsız)")
    ap.add_argument("--poll", type=float, default=5, help="Döngüler arası bekleme (sn)")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    db = _db(a.db)
    if a.report:
        print(report(db))
        return
    start_closed = db.execute("SELECT COUNT(*) FROM paper_trades WHERE result IS NOT NULL").fetchone()[0]
    print(f"Sanal işlem motoru başladı: {len(a.pairs)} çift, {len(STRATEGIES)} strateji. "
          f"Hiçbir platformda işlem açılmaz.", flush=True)
    try:
        while True:
            step(db, a.pairs, STRATEGIES, log=lambda m: print(m, flush=True))
            closed = db.execute("SELECT COUNT(*) FROM paper_trades WHERE result IS NOT NULL").fetchone()[0]
            if a.max_trades and closed - start_closed >= a.max_trades:
                break
            time.sleep(a.poll)
    except KeyboardInterrupt:
        pass
    print("\n" + report(db))


if __name__ == "__main__":
    main()
