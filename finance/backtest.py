"""Basit strateji backtest'leri.

Ajan bir al/sat önerisi yapmadan önce stratejinin o sembolde geçmişte nasıl
çalıştığını ölçer. Sonuçlar geçmiş veridir; geleceği garanti etmez.
Komisyon her işlemde (giriş + çıkış) uygulanır.
"""

from __future__ import annotations

import pandas as pd

from .indicators import atr, bollinger, macd, rsi, sma

STRATEGIES = {
    "sma_cross": "SMA20 SMA50'yi yukarı kesince al, aşağı kesince sat",
    "rsi_reversion": "RSI 30 altına inince al, 55 üstüne çıkınca sat",
    "macd_trend": "MACD histogramı pozitife dönünce ve fiyat SMA200 üstündeyse al, negatife dönünce sat",
    "bollinger_reversion": "Fiyat alt bandın altına inince al, orta banda dönünce sat",
}


def _signals(df: pd.DataFrame, strategy: str) -> tuple[pd.Series, pd.Series]:
    c = df["close"]
    if strategy == "sma_cross":
        f, s = sma(c, 20), sma(c, 50)
        entry = (f > s) & (f.shift() <= s.shift())
        exit_ = (f < s) & (f.shift() >= s.shift())
    elif strategy == "rsi_reversion":
        r = rsi(c)
        entry = r < 30
        exit_ = r > 55
    elif strategy == "macd_trend":
        _, _, h = macd(c)
        trend = c > sma(c, 200) if len(c) >= 200 else c > sma(c, 50)
        entry = (h > 0) & (h.shift() <= 0) & trend
        exit_ = (h < 0) & (h.shift() >= 0)
    elif strategy == "bollinger_reversion":
        lo, mid, _ = bollinger(c)
        entry = c < lo
        exit_ = c > mid
    else:
        raise ValueError(f"Bilinmeyen strateji: {strategy}. Seçenekler: {', '.join(STRATEGIES)}")
    return entry.fillna(False), exit_.fillna(False)


def run(
    df: pd.DataFrame,
    strategy: str,
    fee_pct: float = 0.1,
    stop_atr: float | None = 2.0,
) -> dict:
    """Tek pozisyonlu (long-only) backtest. stop_atr verilirse giriş anındaki
    ATR'nin bu katı kadar zarar-kes uygulanır."""
    entry, exit_ = _signals(df, strategy)
    a = atr(df)
    fee = fee_pct / 100
    trades = []
    in_pos = False
    entry_price = stop = 0.0
    entry_time = None

    for i in range(1, len(df)):
        t = df.index[i]
        row = df.iloc[i]
        if in_pos:
            if stop_atr and row["low"] <= stop:
                trades.append((entry_time, t, entry_price, stop, "stop"))
                in_pos = False
            elif exit_.iloc[i]:
                trades.append((entry_time, t, entry_price, row["close"], "signal"))
                in_pos = False
        elif entry.iloc[i]:
            in_pos = True
            entry_price = row["close"]
            entry_time = t
            stop = entry_price - stop_atr * a.iloc[i] if stop_atr else 0.0

    open_trade = None
    if in_pos:
        open_trade = {"entry_time": str(entry_time), "entry_price": round(entry_price, 6)}

    rets = [(x / e) * (1 - fee) ** 2 - 1 for _, _, e, x, _ in trades]
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in rets:
        equity *= 1 + r
        peak = max(peak, equity)
        max_dd = min(max_dd, equity / peak - 1)

    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]
    buy_hold = df["close"].iloc[-1] / df["close"].iloc[0] - 1
    gross_loss = abs(sum(losses))

    return {
        "strategy": strategy,
        "description": STRATEGIES[strategy],
        "period": f"{df.index[0].date()} → {df.index[-1].date()}",
        "candles": len(df),
        "trades": len(rets),
        "win_rate_pct": round(len(wins) / len(rets) * 100, 1) if rets else None,
        "total_return_pct": round((equity - 1) * 100, 2),
        "buy_and_hold_pct": round(float(buy_hold) * 100, 2),
        "avg_win_pct": round(sum(wins) / len(wins) * 100, 2) if wins else None,
        "avg_loss_pct": round(sum(losses) / len(losses) * 100, 2) if losses else None,
        "profit_factor": round(sum(wins) / gross_loss, 2) if gross_loss else None,
        "max_drawdown_pct": round(max_dd * 100, 2),
        "open_position": open_trade,
        "reliable": len(rets) >= 20,
        "warning": None if len(rets) >= 20 else "20'den az işlem: istatistik güvenilir değil",
    }


def compare(df: pd.DataFrame, fee_pct: float = 0.1) -> list[dict]:
    """Tüm stratejileri çalıştırır, toplam getiriye göre sıralar."""
    results = [run(df, s, fee_pct) for s in STRATEGIES]
    return sorted(results, key=lambda r: r["total_return_pct"], reverse=True)
