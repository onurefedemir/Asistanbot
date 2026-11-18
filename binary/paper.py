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

from . import backtest, data, selector
from . import round2 as R2
from . import strategies as S  # noqa: F401  (_single ile eski stratejiler eklenebilir)

PAYOUT = 0.85
STAKE = 10.0


@dataclass
class Strategy:
    name: str
    # fn(px, pair): px = tüm çiftlerin kapanmış 1 dk kapanışları (sütun = çift, index = zaman);
    # px ile aynı uzunlukta sinyal dizisi döndürür (+1 CALL, -1 PUT, 0 yok)
    fn: Callable[[pd.DataFrame, str], np.ndarray]
    expiry: int  # dakika


def _single(f):
    """Yalnızca kendi çiftinin kapanışını kullanan strateji fonksiyonunu sarar."""
    def run(px, pair):
        c = px[pair]
        out = np.zeros(len(px), dtype=int)
        ok = c.notna().to_numpy()
        out[ok] = np.asarray(f(c[ok].reset_index(drop=True)))
        return out
    return run


# 1. turun stratejileri (zscore, roc, rsi, streak) gerçekçi testte başa başı geçemedi → çıkarıldı.
# Yerine 2. turun çiftler arası aileleri: her ailenin eğitim döneminde en iyi ayarı.
# Hiçbiri testte kanıtlanmış değil; canlıda seçici ölçecek.
STRATEGIES = [
    Strategy("leadlag_k2_z2.5_1dk", lambda px, p: R2.lead_lag(px, p, k=2, z=2.5), 1),
    Strategy("triangle_n240_z2.5_3dk", lambda px, p: R2.triangle(px, p, n=240, z=2.5), 3),
    Strategy("usdbasket_k5_z2_3dk", lambda px, p: R2.usd_basket(px, p, k=5, z=2.0), 3),
    Strategy("volhigh_z2.5_5dk", lambda px, p: R2.vol_filtered(px, p, regime="high", z=2.5), 5),
]


def _db(path: str) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.execute(
        """CREATE TABLE IF NOT EXISTS paper_trades(
            id INTEGER PRIMARY KEY AUTOINCREMENT, strategy TEXT, pair TEXT, direction INTEGER,
            signal_ts INTEGER, entry_ts REAL, entry_price REAL, expiry INTEGER,
            exit_ts REAL, exit_price REAL, result TEXT, pnl REAL)"""
    )
    cols = {r[1] for r in db.execute("PRAGMA table_info(paper_trades)")}
    if "selected" not in cols:
        # selected=1: seçicinin "gerçekte yapardım" dediği işlem; 0: yalnızca gölgede izlenen sinyal
        db.execute("ALTER TABLE paper_trades ADD COLUMN selected INTEGER DEFAULT 1")
    return db


def _quotes(pair: str, now: int) -> pd.DataFrame | None:
    try:
        df = data.fetch_chunk(pair, now - 8 * 3600, now + 60)  # üçgen (240) ve oynaklık filtresi (300+) için
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

    quotes = {p: q for p in pairs if (q := _quotes(p, now)) is not None}

    # 1) Vadesi dolan işlemleri anlık fiyatla kapat
    for tid, sname, tpair, d, entry_ts, entry_price, expiry in open_rows:
        if tpair not in quotes or time.time() < entry_ts + expiry * 60:
            continue
        live_price = float(quotes[tpair]["close"].iloc[-1])
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

    # 2) Yeni sinyaller: yalnızca kapanmış mumlarla (backtest ile aynı), tüm çiftler birlikte
    done = {p: q[q["ts"] <= now - 60] for p, q in quotes.items()}
    done = {p: d for p, d in done.items() if len(d) >= 60}
    if not done:
        db.commit()
        return closed
    px = pd.DataFrame(
        {p: pd.Series(d["close"].to_numpy(), index=pd.to_datetime(d["ts"], unit="s", utc=True)) for p, d in done.items()}
    ).sort_index()
    for pair, d in done.items():
        signal_ts = int(d["ts"].iloc[-1])
        live_ts = int(quotes[pair]["ts"].iloc[-1])
        live_price = float(quotes[pair]["close"].iloc[-1])  # içinde bulunulan dakikanın son fiyatı = anlık fiyat
        # Sinyal mumu kapanalı 45 sn'den fazla olduysa geç kalınmıştır
        if now - (signal_ts + 60) > 45 or live_ts <= signal_ts:
            continue
        row = px.index.get_loc(pd.Timestamp(signal_ts, unit="s", tz="UTC"))
        for st in strategies:
            if (st.name, pair) in open_keys:
                continue
            sig = int(np.nan_to_num(np.asarray(st.fn(px, pair), dtype=float)[row]))
            if not sig:
                continue
            dup = db.execute(
                "SELECT 1 FROM paper_trades WHERE strategy=? AND pair=? AND signal_ts=?", (st.name, pair, signal_ts)
            ).fetchone()
            if dup:
                continue
            chosen = selector.choose(db, st.name, PAYOUT)
            cur = db.execute(
                "INSERT INTO paper_trades(strategy,pair,direction,signal_ts,entry_ts,entry_price,expiry,selected)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (st.name, pair, sig, signal_ts, time.time(), live_price, st.expiry, int(chosen)),
            )
            open_keys.add((st.name, pair))
            log(f"[{time.strftime('%H:%M:%S')}] #{cur.lastrowid} AÇ {pair} {'CALL ↑' if sig > 0 else 'PUT ↓'} "
                f"{st.expiry}dk @ {live_price:.5f}  ({st.name}){'' if chosen else '  [gölge]'}")
    db.commit()
    return closed


def report(db: sqlite3.Connection) -> str:
    rows = db.execute(
        "SELECT strategy, pair, result, pnl, selected FROM paper_trades WHERE result IS NOT NULL"
    ).fetchall()
    if not rows:
        return "Henüz kapanmış işlem yok."
    df = pd.DataFrame(rows, columns=["strategy", "pair", "result", "pnl", "selected"])

    def summary(d, title):
        code = d["result"].map({"win": 1, "loss": -1, "tie": 0}).to_numpy(dtype=np.int8)
        s = backtest.stats(code, PAYOUT)
        return [
            f"{title}: {len(d)} işlem (kazanç {int((d.result == 'win').sum())}, "
            f"kayıp {int((d.result == 'loss').sum())}, iade {int((d.result == 'tie').sum())})",
            f"  kazanma %{s['win_rate']} | başa baş %{s['breakeven']} | K/Z {d.pnl.sum():+.2f} | p={s['p_value']}",
        ]

    lines = summary(df, "Tüm sinyaller")
    lines += summary(df[df.selected == 1], "Seçicinin seçtikleri")
    lines += [
        f"(işlem başı {STAKE:.0f} birim, ödeme %{PAYOUT*100:.0f}; p < 0.01 olmadıkça avantaj kanıtlanmış sayılmaz)",
        "",
        f"{'strateji':<22}{'işlem':>6}{'kazanma':>9}{'P(>başa baş)':>14}  durum",
    ]
    for r in selector.table(db, PAYOUT):
        lines.append(f"{r['strategy']:<22}{r['trades']:>6}{'%' + str(r['win_rate']):>9}"
                     f"{'%' + str(r['prob_above_breakeven']):>14}  {r['status']}")
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
    ap.add_argument("--ml", action="store_true",
                    help="Makine öğrenmesi stratejilerini de ekle (günde bir kez yeni veriyle yeniden eğitilir)")
    ap.add_argument("--data-db", default=data.DB, help="ML eğitimi için 1 dk veri veritabanı")
    a = ap.parse_args()
    db = _db(a.db)
    if a.report:
        print(report(db))
        return
    start_closed = db.execute("SELECT COUNT(*) FROM paper_trades WHERE result IS NOT NULL").fetchone()[0]
    ml_state = {"bundle": None}

    def ml_strategies() -> list[Strategy]:
        from . import ml

        b = ml_state["bundle"]
        if b is None or time.time() - b["trained_at"] > 24 * 3600:
            print("ML: veri güncelleniyor ve model yeniden eğitiliyor...", flush=True)
            data.update(path=a.data_db)
            ml_state["bundle"] = b = ml.train(ml.load_frames(a.data_db))
            print("ML: model hazır.", flush=True)
        return [
            Strategy(f"ml_{e}dk", _single(lambda c, e=e: ml.predict_signal(b, c, e)), e) for e in (1, 5)
        ]

    n_strats = len(STRATEGIES) + (2 if a.ml else 0)
    print(f"Sanal işlem motoru başladı: {len(a.pairs)} çift, {n_strats} strateji. "
          f"Hiçbir platformda işlem açılmaz.", flush=True)
    try:
        while True:
            strategies = STRATEGIES + (ml_strategies() if a.ml else [])
            step(db, a.pairs, strategies, log=lambda m: print(m, flush=True))
            closed = db.execute("SELECT COUNT(*) FROM paper_trades WHERE result IS NOT NULL").fetchone()[0]
            if a.max_trades and closed - start_closed >= a.max_trades:
                break
            time.sleep(a.poll)
    except KeyboardInterrupt:
        pass
    print("\n" + report(db))


if __name__ == "__main__":
    main()
