"""Canlı sinyal + demo işlem günlüğü (PC'de çalışır, işlem AÇMAZ).

Amaç: Backtest'te yalnızca anında girişte (gecikmesiz) görülen kazancın, Pocket Option'ın
kendi fiyat akışında gerçekten yakalanıp yakalanamayacağını DEMO hesapla ölçmek.

Kullanım:
    python -m binary.live                 # sinyalleri izle; her sinyalde sesli uyarı
    python -m binary.live --journal       # demo sonuçlarını gir (k = kazanç, z = kayıp, e = eşit)
    python -m binary.live --stats         # demo sonuçlarının istatistiği

Akış: sinyal gelince Pocket Option DEMO hesabında aynı çifte, aynı yönde, belirtilen vadeyle
hemen işlem açın; vade dolunca `--journal` ile sonucu girin. 300+ işlemden sonra `--stats`
kazanma oranının başa başın anlamlı şekilde üstünde olup olmadığını söyler.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time

import numpy as np

from . import backtest, data
from . import strategies as S

# Gecikmesiz backtest'te en güçlü görünen adaylar. Gecikmeli testte kazançları kayboldu;
# demo bunların gerçek olup olmadığını gösterecek.
CANDIDATES = [
    ("zscore_n10_z2.5", lambda c: S.zscore_reversion(c, n=10, z=2.5), 2),
    ("roc_n1_z3", lambda c: S.roc_reversion(c, n=1, z=3.0), 1),
]
DB = "binary.db"


def _db(path=DB):
    db = sqlite3.connect(path)
    db.execute(
        "CREATE TABLE IF NOT EXISTS signals(id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, pair TEXT,"
        " strategy TEXT, direction TEXT, expiry INTEGER, price REAL, result TEXT)"
    )
    return db


def watch(pairs, path=DB, poll=5):
    db = _db(path)
    seen = set()
    print("Sinyaller izleniyor (Ctrl+C ile çık). Yalnızca DEMO hesapta deneyin.\n")
    while True:
        now = int(time.time())
        for pair in pairs:
            try:
                df = data.fetch_chunk(pair, now - 3 * 3600, now)
            except Exception as e:
                print(f"{pair}: veri alınamadı ({e})")
                continue
            if len(df) < 60:
                continue
            df = df.set_index("ts")
            # Son satır henüz kapanmamış dakikadır: backtest ile aynı olsun diye yalnızca kapanmış mumlar
            df = df[df.index <= now - 60]
            close = df["close"].reset_index(drop=True)
            last_ts = int(df.index[-1])
            for name, fn, expiry in CANDIDATES:
                sig = int(np.asarray(fn(close))[-1])
                key = (pair, name, last_ts)
                # Mum kapanalı 30 sn'den fazla olduysa sinyal bayattır (backtest'teki giriş anı geçti)
                if sig and key not in seen and now - (last_ts + 60) < 30:
                    seen.add(key)
                    direction = "CALL ↑" if sig > 0 else "PUT ↓"
                    db.execute(
                        "INSERT INTO signals(ts,pair,strategy,direction,expiry,price) VALUES(?,?,?,?,?,?)",
                        (last_ts, pair, name, direction, expiry, float(close.iloc[-1])),
                    )
                    db.commit()
                    sid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
                    print(f"\a[{time.strftime('%H:%M:%S')}] #{sid} {pair} {direction} vade {expiry} dk ({name})")
            time.sleep(0.3)
        time.sleep(poll)


def journal(path=DB):
    db = _db(path)
    rows = db.execute(
        "SELECT id, ts, pair, direction, expiry, strategy FROM signals WHERE result IS NULL ORDER BY id"
    ).fetchall()
    if not rows:
        print("Sonucu girilmemiş sinyal yok.")
        return
    print("Her sinyal için: k = kazanç, z = kayıp, e = eşit/iade, a = işlem açmadım, boş = atla")
    for sid, ts, pair, d, e, name in rows:
        t = time.strftime("%m-%d %H:%M", time.localtime(ts))
        ans = input(f"#{sid} {t} {pair} {d} {e}dk ({name}): ").strip().lower()
        val = {"k": "win", "z": "loss", "e": "tie", "a": "skipped"}.get(ans)
        if val:
            db.execute("UPDATE signals SET result=? WHERE id=?", (val, sid))
            db.commit()


def stats(path=DB, payout=0.85):
    db = _db(path)
    for name in [c[0] for c in CANDIDATES] + [None]:
        q = "SELECT result FROM signals WHERE result IN ('win','loss','tie')"
        args = ()
        if name:
            q += " AND strategy=?"
            args = (name,)
        res = np.array([{"win": 1, "loss": -1, "tie": 0}[r[0]] for r in db.execute(q, args)], dtype=np.int8)
        s = backtest.stats(res, payout)
        label = name or "TOPLAM"
        print(f"{label:<18} işlem {s['trades']:>4}  kazanma %{s['win_rate']}  başa baş %{s['breakeven']}  "
              f"işlem başı beklenen %{s['ev_per_trade']}  p={s['p_value']}")
    print("\nKarar kuralı: en az 300 işlem ve p < 0.01 olmadan gerçek paraya geçmeyin.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--journal", action="store_true")
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--payout", type=float, default=0.85)
    ap.add_argument("--pairs", nargs="*", default=["EURUSD", "GBPUSD", "USDJPY", "USDCAD", "EURJPY"])
    ap.add_argument("--db", default=DB)
    a = ap.parse_args()
    try:
        if a.journal:
            journal(a.db)
        elif a.stats:
            stats(a.db, a.payout)
        else:
            watch(a.pairs, a.db)
    except KeyboardInterrupt:
        sys.exit(0)
