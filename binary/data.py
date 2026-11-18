"""Döviz çiftlerinin 1 dakikalık verisini Yahoo Finance'ten toplar ve SQLite'ta biriktirir.

Yahoo 1 dakikalık veriyi yalnızca son ~30 gün için, her istekte en fazla 7 gün verir.
`python -m binary.data` her çalıştırıldığında eksik kısmı ekler; PC'de günde bir
kez çalıştırılırsa geçmiş zamanla büyür (daha güvenilir istatistik için gerekli).
"""

from __future__ import annotations

import argparse
import sqlite3
import time

import pandas as pd
import requests

# Pocket Option'da OTC olmayan (gerçek piyasa) ana çiftler
PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "EURJPY", "EURGBP", "GBPJPY", "AUDCAD"]
URL = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}=X"
HEADERS = {"User-Agent": "Mozilla/5.0"}
DB = "binary.db"


def _db(path: str = DB) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.execute(
        "CREATE TABLE IF NOT EXISTS candles(pair TEXT, ts INTEGER, open REAL, high REAL, low REAL, close REAL,"
        " PRIMARY KEY(pair, ts))"
    )
    return db


def fetch_chunk(pair: str, start: int, end: int) -> pd.DataFrame:
    r = requests.get(
        URL.format(sym=pair),
        params={"interval": "1m", "period1": start, "period2": end},
        headers=HEADERS,
        timeout=20,
    )
    r.raise_for_status()
    res = r.json()["chart"]["result"]
    if not res or "timestamp" not in res[0]:
        return pd.DataFrame()
    q = res[0]["indicators"]["quote"][0]
    df = pd.DataFrame(
        {"ts": res[0]["timestamp"], "open": q["open"], "high": q["high"], "low": q["low"], "close": q["close"]}
    ).dropna()
    # Not: EURUSD/GBPUSD/AUDUSD için Yahoo yalnızca dakika kapanışını verir (O=H=L=C).
    # Stratejiler bu yüzden yalnızca kapanış fiyatını kullanır.
    return df


def update(pairs=PAIRS, days: int = 29, path: str = DB) -> dict:
    """Her çift için son kayıttan bugüne kadar eksik veriyi indirir."""
    db = _db(path)
    now = int(time.time())
    added = {}
    for pair in pairs:
        # Pencerenin tamamı her seferinde istenir (INSERT OR IGNORE): ara boşluklar da dolar.
        start = now - days * 86400
        before = db.execute("SELECT COUNT(*) FROM candles WHERE pair=?", (pair,)).fetchone()[0]
        while start < now:
            end = min(start + 7 * 86400, now)
            try:
                df = fetch_chunk(pair, start, end)
            except Exception as e:
                print(f"{pair} {time.strftime('%m-%d', time.gmtime(start))}: {e}")
                df = pd.DataFrame()
            if len(df):
                db.executemany(
                    "INSERT OR IGNORE INTO candles VALUES(?,?,?,?,?,?)",
                    [(pair, int(r.ts), r.open, r.high, r.low, r.close) for r in df.itertuples()],
                )
            start = end
            time.sleep(0.5)
        db.commit()
        added[pair] = db.execute("SELECT COUNT(*) FROM candles WHERE pair=?", (pair,)).fetchone()[0] - before
    db.close()
    return added


def load(pair: str, path: str = DB) -> pd.DataFrame:
    db = _db(path)
    df = pd.read_sql_query(
        "SELECT ts, open, high, low, close FROM candles WHERE pair=? ORDER BY ts", db, params=(pair,)
    )
    db.close()
    df.index = pd.to_datetime(df.pop("ts"), unit="s", utc=True)
    return df


def export_csv(folder: str, path: str = DB) -> list[str]:
    """Veriyi aylık sıkıştırılmış CSV'lere yazar (folder/YYYY-MM.csv.gz).
    Git'te yalnızca içinde bulunulan ayın dosyası değişir; depo şişmez."""
    import os

    os.makedirs(folder, exist_ok=True)
    db = _db(path)
    df = pd.read_sql_query("SELECT * FROM candles ORDER BY ts, pair", db)
    db.close()
    months = pd.to_datetime(df["ts"], unit="s", utc=True).dt.strftime("%Y-%m")
    written = []
    for month, part in df.groupby(months):
        f = os.path.join(folder, f"{month}.csv.gz")
        # mtime=0: içerik aynıysa dosya baytları da aynı kalır (gereksiz commit olmaz)
        part.to_csv(f, index=False, compression={"method": "gzip", "mtime": 0})
        written.append(f)
    return written


def import_csv(folder: str, path: str = DB) -> int:
    """export_csv ile yazılmış dosyaları veritabanına ekler."""
    import glob

    db = _db(path)
    n = 0
    for f in sorted(glob.glob(f"{folder}/*.csv.gz")):
        df = pd.read_csv(f)
        db.executemany(
            "INSERT OR IGNORE INTO candles VALUES(?,?,?,?,?,?)",
            df[["pair", "ts", "open", "high", "low", "close"]].itertuples(index=False, name=None),
        )
        n += len(df)
    db.commit()
    db.close()
    return n


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="1 dakikalık döviz verisi topla")
    p.add_argument("--pairs", nargs="*", default=PAIRS)
    p.add_argument("--db", default=DB)
    p.add_argument("--import-csv", metavar="KLASÖR", help="Önce bu klasördeki aylık CSV'leri içe aktar")
    p.add_argument("--export-csv", metavar="KLASÖR", help="Sonra veriyi bu klasöre aylık CSV olarak yaz")
    p.add_argument("--no-update", action="store_true", help="İnternetten veri indirme")
    a = p.parse_args()
    if a.import_csv:
        print(f"İçe aktarılan satır: {import_csv(a.import_csv, a.db)}")
    added = {} if a.no_update else update(a.pairs, path=a.db)
    if a.export_csv:
        print(f"Yazılan dosyalar: {', '.join(export_csv(a.export_csv, a.db))}")
    for k, v in added.items():
        print(f"{k}: +{v} mum")
