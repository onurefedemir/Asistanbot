"""TradingView "UT Bot Alerts" göstergesinin birebir Python karşılığı ve ikili opsiyon testi.

Pine Script mantığı (açık kaynak, QuantNomad / HPotter):
    xATR  = atr(c)                        # RMA ile ortalama gerçek aralık
    nLoss = a * xATR
    stop  = önceki stop'a göre fiyatı takip eden ATR izleyen stop
    buy   = close > stop ve close stop'u yukarı kesti
    sell  = close < stop ve close stop'u aşağı kesti

Varsayılan ayarlar kullanıcının grafiğindekilerdir: a (Key Value) = 1, c (ATR Period) = 10,
Heikin Ashi kapalı. Sinyal mum kapanışında oluşur (TradingView alarmı gibi).

Kullanım:
    python -m binary.utbot                     # Yahoo 1 dk (10 parite + AUDCHF), son 30 gün
    python -m binary.utbot --pocket results_20261116.jsonl   # Pocket'ın kendi verisi + gerçek ödemeler
"""

from __future__ import annotations

import argparse
import time

import numpy as np
import pandas as pd

from . import backtest, data

EXPIRIES = [1, 2, 3, 5, 15, 30]


def _hl_reliable(df: pd.DataFrame) -> bool:
    """Yahoo bazı paritelerde bozuk high/low veriyor (ör. AUDCHF'de low, kapanışın ~7 pip altında).
    Mum gövdesi (|kapanış-açılış|) aralığın çok küçük bir kısmıysa high/low güvenilmez sayılır."""
    if not {"high", "low", "open"} <= set(df.columns):
        return False
    rng = (df["high"] - df["low"])
    if (rng > 0).mean() < 0.5:
        return False
    body = (df["close"] - df["open"]).abs()
    return float(body.median() / rng.median()) > 0.2


def ut_bot(df: pd.DataFrame, key: float = 1.0, atr_period: int = 10, use_hl: bool | None = False) -> np.ndarray:
    """+1 Buy, -1 Sell, 0 sinyal yok. df: close (varsa open/high/low) sütunları.
    use_hl=False (varsayılan): gerçek aralık ≈ |Δkapanış|. Yahoo'nun high/low'unda ara sıra uç
    değerler ATR'yi şişiriyor; bu modda kullanıcının 18 Kasım AUDCHF 1 dk ekran görüntüsündeki
    sinyaller 1-2 dk farkla yeniden üretildi. use_hl=None: high/low güvenilir görünüyorsa kullan."""
    c = df["close"].to_numpy(dtype=float)
    if use_hl is None:
        use_hl = _hl_reliable(df)
    if use_hl:
        h, lo = df["high"].to_numpy(float), df["low"].to_numpy(float)
        prev = np.r_[np.nan, c[:-1]]
        tr = np.nanmax(np.vstack([h - lo, np.abs(h - prev), np.abs(lo - prev)]), axis=0)
    else:  # yalnızca kapanış varsa (Yahoo EURUSD vb., Pocket kaydı): gerçek aralık ≈ |Δkapanış|
        tr = np.abs(np.diff(c, prepend=np.nan))
    if len(tr):
        tr[0] = np.nan
    # Pine ta.atr = RMA(tr, n): ilk değer ilk n'in ortalaması, sonra alpha = 1/n
    atr = pd.Series(tr).ewm(alpha=1 / atr_period, adjust=False, min_periods=atr_period).mean().to_numpy()
    n_loss = key * atr
    stop = np.zeros(len(c))
    sig = np.zeros(len(c), dtype=int)
    for i in range(1, len(c)):
        ps = stop[i - 1]
        if np.isnan(n_loss[i]):
            stop[i] = ps
            continue
        if c[i] > ps and c[i - 1] > ps:
            stop[i] = max(ps, c[i] - n_loss[i])
        elif c[i] < ps and c[i - 1] < ps:
            stop[i] = min(ps, c[i] + n_loss[i])
        elif c[i] > ps:
            stop[i] = c[i] - n_loss[i]
        else:
            stop[i] = c[i] + n_loss[i]
        # ema(src, 1) = src; crossover(src, stop) / crossover(stop, src)
        above = c[i] > stop[i] and c[i - 1] <= stop[i - 1]
        below = c[i] < stop[i] and c[i - 1] >= stop[i - 1]
        if above:
            sig[i] = 1
        elif below:
            sig[i] = -1
    sig[: atr_period + 1] = 0  # ısınma dönemi
    return sig


def _row(name, res, payouts):
    r = np.concatenate([x for x, _ in res]) if res else np.array([], np.int8)
    pnl = sum(float(((x == 1) * p - (x == -1)).sum()) for x, p in res)
    n = int((r != 0).sum())
    w = int((r == 1).sum())
    be = np.mean(sum(([1 / (1 + p)] * int((x != 0).sum()) for x, p in res), [])) if n else float("nan")
    import math
    z = (w - n * be - 0.5) / math.sqrt(n * be * (1 - be)) if n else float("nan")
    p = 0.5 * math.erfc(z / math.sqrt(2)) if n else float("nan")
    return {**name, "trades": n, "win_rate": round(w / n * 100, 2) if n else None,
            "be_pct": round(be * 100, 2) if n else None,
            "ev_per_trade": round(pnl / n * 100, 2) if n else None, "p": round(p, 4) if n else None}


def evaluate(frames: dict[str, pd.DataFrame], payouts: dict[str, float], key=1.0, atr_period=10,
             expiries=EXPIRIES, delays=(0, 1)) -> pd.DataFrame:
    rows = []
    sigs = {p: ut_bot(df, key, atr_period) for p, df in frames.items()}
    for d in delays:
        for e in expiries:
            res = [(backtest.trades(df, sigs[p], e, delay=d), payouts.get(p, 0.85)) for p, df in frames.items()]
            rows.append(_row({"delay": d, "expiry": e}, res, payouts))
    return pd.DataFrame(rows)


def yahoo_frames(days: int = 29) -> dict[str, pd.DataFrame]:
    now = int(time.time())
    out = {}
    for p in data.PAIRS + ["AUDCHF"]:
        parts = []
        start = now - days * 86400
        while start < now:
            end = min(start + 7 * 86400, now)
            try:
                parts.append(data.fetch_chunk(p, start, end))
            except Exception as ex:
                print(f"{p}: {ex}")
            start = end
            time.sleep(0.3)
        df = pd.concat(parts).drop_duplicates("ts").sort_values("ts")
        df.index = pd.to_datetime(df.pop("ts"), unit="s", utc=True)
        if len(df) > 1000:
            out[p] = df
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pocket", help="Pocket canlı kayıt dosyası (results_*.jsonl)")
    ap.add_argument("--key", type=float, default=1.0)
    ap.add_argument("--atr", type=int, default=10)
    ap.add_argument("--payout", type=float, default=0.85, help="Yahoo testi için ödeme")
    a = ap.parse_args()
    if a.pocket:
        from . import pocket_log
        log = pocket_log.load(a.pocket)
        px = pocket_log.price_series(log)
        frames = {p: px[[p]].rename(columns={p: "close"}).dropna() for p in px.columns}
        payouts = pocket_log.payout_by_symbol(log)
        src = f"Pocket'ın kendi fiyatları ({px.index.min():%Y-%m-%d %H:%M}–{px.index.max():%H:%M} UTC), gerçek ödemeler"
    else:
        frames = yahoo_frames()
        payouts = {p: a.payout for p in frames}
        src = f"Yahoo 1 dk, {len(frames)} parite, ödeme %{a.payout * 100:.0f}"
    r = evaluate(frames, payouts, a.key, a.atr)
    print(f"UT Bot Alerts (Key={a.key:g}, ATR={a.atr}) — {src}")
    print("delay 0: sinyal mumunun kapanışında giriş (iyimser, saniyeler içinde tıklama); delay 1: 1 mum sonra\n")
    print(r.to_string(index=False))
    alpha = 0.05 / len(r)
    print(f"\nBonferroni eşiği p < {alpha:.4f}; geçen: {int((r.p < alpha).sum())}")


if __name__ == "__main__":
    main()
