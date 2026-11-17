"""Teknik indikatörler ve özet analiz (yalnızca pandas)."""

from __future__ import annotations

import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    delta = s.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = gain / loss.replace(0, float("nan"))
    return (100 - 100 / (1 + rs)).fillna(100)


def macd(s: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    line = ema(s, fast) - ema(s, slow)
    sig = ema(line, signal)
    return line, sig, line - sig


def bollinger(s: pd.Series, n: int = 20, k: float = 2.0):
    mid = sma(s, n)
    std = s.rolling(n).std()
    return mid - k * std, mid, mid + k * std


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev = df["close"].shift()
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def analyze(df: pd.DataFrame) -> dict:
    """Son muma göre indikatör değerleri ve basit bir puanlama döndürür.

    Puan -5 (güçlü sat) ile +5 (güçlü al) arasındadır. Bu bir tavsiye değil,
    ajanın karar verirken kullandığı bir girdidir.
    """
    if len(df) < 60:
        raise ValueError("Analiz için en az 60 mum gerekli.")
    c = df["close"]
    r = rsi(c)
    m_line, m_sig, m_hist = macd(c)
    lo, mid, up = bollinger(c)
    s20, s50 = sma(c, 20), sma(c, 50)
    s200 = sma(c, 200) if len(c) >= 200 else None
    a = atr(df)

    last = float(c.iloc[-1])
    score = 0
    notes = []

    rv = float(r.iloc[-1])
    if rv < 30:
        score += 1; notes.append(f"RSI {rv:.0f}: aşırı satım")
    elif rv > 70:
        score -= 1; notes.append(f"RSI {rv:.0f}: aşırı alım")

    if m_hist.iloc[-1] > 0 and m_hist.iloc[-2] <= 0:
        score += 1; notes.append("MACD yukarı kesti")
    elif m_hist.iloc[-1] < 0 and m_hist.iloc[-2] >= 0:
        score -= 1; notes.append("MACD aşağı kesti")
    else:
        score += 0.5 if m_hist.iloc[-1] > 0 else -0.5

    if s20.iloc[-1] > s50.iloc[-1]:
        score += 1; notes.append("SMA20 > SMA50 (kısa vadeli yükseliş)")
    else:
        score -= 1; notes.append("SMA20 < SMA50 (kısa vadeli düşüş)")

    if s200 is not None:
        if last > s200.iloc[-1]:
            score += 1; notes.append("Fiyat SMA200 üzerinde (uzun vadeli trend yukarı)")
        else:
            score -= 1; notes.append("Fiyat SMA200 altında (uzun vadeli trend aşağı)")

    if last < lo.iloc[-1]:
        score += 1; notes.append("Fiyat alt Bollinger bandının altında")
    elif last > up.iloc[-1]:
        score -= 1; notes.append("Fiyat üst Bollinger bandının üstünde")

    atr_v = float(a.iloc[-1])
    return {
        "price": round(last, 6),
        "change_pct_1": round(float(c.pct_change().iloc[-1] * 100), 2),
        "change_pct_20": round(float((c.iloc[-1] / c.iloc[-21] - 1) * 100), 2),
        "rsi14": round(rv, 2),
        "macd_hist": round(float(m_hist.iloc[-1]), 6),
        "sma20": round(float(s20.iloc[-1]), 6),
        "sma50": round(float(s50.iloc[-1]), 6),
        "sma200": round(float(s200.iloc[-1]), 6) if s200 is not None else None,
        "bb_lower": round(float(lo.iloc[-1]), 6),
        "bb_upper": round(float(up.iloc[-1]), 6),
        "atr14": round(atr_v, 6),
        "volatility_pct": round(atr_v / last * 100, 2),
        "suggested_stop_loss": round(last - 2 * atr_v, 6),
        "suggested_take_profit": round(last + 3 * atr_v, 6),
        "score": round(score, 1),
        "notes": notes,
    }
