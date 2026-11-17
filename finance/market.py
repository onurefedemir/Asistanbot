"""Piyasa verisi.

- Kripto (BTCUSDT, ETHUSDT ...): Binance halka açık API, anahtar gerekmez.
- Hisse / BIST / döviz (THYAO.IS, AAPL, USDTRY=X ...): Yahoo Finance chart API.

Sembolde "USDT", "BUSD" veya "TRY" ile biten ve nokta/eşittir içermeyen
semboller kripto kabul edilir; geri kalanı Yahoo'ya gider.
"""

from __future__ import annotations

import pandas as pd
import requests

BINANCE = "https://api.binance.com/api/v3"
YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
HEADERS = {"User-Agent": "Mozilla/5.0 (Asistanbot)"}

# Kullanıcı dostu aralık adları -> (binance interval, yahoo interval)
INTERVALS = {
    "15m": ("15m", "15m"),
    "1h": ("1h", "60m"),
    "4h": ("4h", "60m"),  # Yahoo'da 4h yok, 1 saatlik veri kullanılır
    "1d": ("1d", "1d"),
    "1w": ("1w", "1wk"),
}


def is_crypto(symbol: str) -> bool:
    s = symbol.upper()
    return "." not in s and "=" not in s and s.endswith(("USDT", "BUSD", "FDUSD", "TRY", "BTC"))


def get_candles(symbol: str, interval: str = "1d", limit: int = 365) -> pd.DataFrame:
    """OHLCV mumlarını döndürür (index: zaman, kolonlar: open high low close volume)."""
    if interval not in INTERVALS:
        raise ValueError(f"Geçersiz aralık: {interval}. Seçenekler: {', '.join(INTERVALS)}")
    symbol = symbol.upper().strip()
    if is_crypto(symbol):
        return _binance_candles(symbol, INTERVALS[interval][0], limit)
    return _yahoo_candles(symbol, INTERVALS[interval][1], limit)


def get_price(symbol: str) -> float:
    symbol = symbol.upper().strip()
    if is_crypto(symbol):
        r = requests.get(f"{BINANCE}/ticker/price", params={"symbol": symbol}, timeout=10)
        r.raise_for_status()
        return float(r.json()["price"])
    df = _yahoo_candles(symbol, "1d", 5)
    return float(df["close"].iloc[-1])


def _binance_candles(symbol: str, interval: str, limit: int) -> pd.DataFrame:
    r = requests.get(
        f"{BINANCE}/klines",
        params={"symbol": symbol, "interval": interval, "limit": min(limit, 1000)},
        timeout=15,
    )
    r.raise_for_status()
    rows = r.json()
    df = pd.DataFrame(
        rows,
        columns=["t", "open", "high", "low", "close", "volume", "ct", "qv", "n", "tb", "tq", "i"],
    )
    df["t"] = pd.to_datetime(df["t"], unit="ms", utc=True)
    df = df.set_index("t")[["open", "high", "low", "close", "volume"]].astype(float)
    return df


def _yahoo_candles(symbol: str, interval: str, limit: int) -> pd.DataFrame:
    # Yahoo, aralığa göre izin verilen en uzun dönemi ister.
    rng = {"15m": "60d", "60m": "730d", "1d": "5y", "1wk": "10y"}[interval]
    r = requests.get(
        YAHOO.format(symbol=symbol),
        params={"interval": interval, "range": rng},
        headers=HEADERS,
        timeout=15,
    )
    r.raise_for_status()
    result = r.json()["chart"]["result"]
    if not result:
        raise ValueError(f"Sembol bulunamadı: {symbol}")
    res = result[0]
    q = res["indicators"]["quote"][0]
    df = pd.DataFrame(
        {
            "open": q["open"],
            "high": q["high"],
            "low": q["low"],
            "close": q["close"],
            "volume": q["volume"],
        },
        index=pd.to_datetime(res["timestamp"], unit="s", utc=True),
    ).dropna()
    return df.tail(limit).astype(float)
