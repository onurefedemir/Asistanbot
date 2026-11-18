"""Kullanıcının TradingView favorilerindeki göstergelerin ikili opsiyon testi.

Göstergeler, yazarlarının yayımladığı açık kaynak mantıkla, varsayılan ayarlarıyla yeniden yazıldı
(TradingView'e bu ortamdan erişilemediği için kaynak kod satır satır karşılaştırılamadı; UT Bot'ta
bu yöntemle kullanıcının grafiğindeki sinyaller 1-2 dk farkla yeniden üretildi). Hepsi yalnızca
kapanış fiyatını kullanır (Yahoo'nun high/low'unda uç değerler var; Pocket kaydında yalnızca fiyat var).

Her fonksiyon: close (pd.Series) → sinyal dizisi (+1 Buy/CALL, -1 Sell/PUT, 0 yok),
sinyal mumun kapanışında, yalnızca o ana kadarki veriyle (pivot tabanlılar pivotu teyit
edildiği mumda, yani `right` mum sonra sinyal verir — TradingView'de de böyledir).

Kullanım:
    python -m binary.tv_indicators
    python -m binary.tv_indicators --pocket results_20261116.jsonl
"""

from __future__ import annotations

import argparse
import math

import numpy as np
import pandas as pd

from . import backtest, utbot
from .strategies import _rsi

EXPIRIES = [1, 5, 15, 30]


def _pivots(x: np.ndarray, left: int, right: int):
    """Teyit edildiği mumda (i) pivot değerini döndürür; pivot mumu i-right'tır."""
    n = len(x)
    ph = np.full(n, np.nan)
    pl = np.full(n, np.nan)
    for i in range(left + right, n):
        j = i - right
        win = x[j - left : i + 1]
        if x[j] == win.max() and (win == x[j]).sum() == 1:
            ph[i] = x[j]
        if x[j] == win.min() and (win == x[j]).sum() == 1:
            pl[i] = x[j]
    return ph, pl


def _atr_close(c: np.ndarray, n: int) -> np.ndarray:
    tr = np.abs(np.diff(c, prepend=np.nan))
    return pd.Series(tr).ewm(alpha=1 / n, adjust=False, min_periods=n).mean().to_numpy()


# --- LuxAlgo: Trendlines with Breaks (uzunluk 14, eğim çarpanı 1, ATR yöntemi) ---
def trendlines_breaks(close: pd.Series, length: int = 14, mult: float = 1.0) -> np.ndarray:
    c = close.to_numpy(float)
    ph, pl = _pivots(c, length, length)
    slope = _atr_close(c, length) / length * mult
    n = len(c)
    sig = np.zeros(n, int)
    upper = lower = np.nan
    sp = sl = 0.0
    upos = dnos = 0
    for i in range(n):
        if not np.isnan(ph[i]):
            sp, upper = slope[i], ph[i]
        elif not np.isnan(upper):
            upper -= sp
        if not np.isnan(pl[i]):
            sl, lower = slope[i], pl[i]
        elif not np.isnan(lower):
            lower += sl
        pu, pd_ = upos, dnos
        upos = 0 if not np.isnan(ph[i]) else (1 if (not np.isnan(upper) and c[i] > upper - sp * length) else upos)
        dnos = 0 if not np.isnan(pl[i]) else (1 if (not np.isnan(lower) and c[i] < lower + sl * length) else dnos)
        if upos > pu:
            sig[i] = 1
        elif dnos > pd_:
            sig[i] = -1
    return sig


# --- LuxAlgo: Trend Regularity Adaptive Moving Average (uzunluk 99) ---
def trama(close: pd.Series, length: int = 99) -> np.ndarray:
    c = close.to_numpy(float)
    s = pd.Series(c)
    hh = np.maximum(np.sign(s.rolling(length).max().diff()), 0)
    ll = np.maximum(np.sign(s.rolling(length).min().diff() * -1), 0)
    tc = (((hh > 0) | (ll > 0)).astype(float).rolling(length).mean() ** 2).to_numpy()
    ama = np.full(len(c), np.nan)
    for i in range(len(c)):
        prev = ama[i - 1] if i and not np.isnan(ama[i - 1]) else c[i]
        ama[i] = prev + (0 if np.isnan(tc[i]) else tc[i]) * (c[i] - prev)
    above = c > ama
    sig = np.zeros(len(c), int)
    sig[1:] = np.where(above[1:] & ~above[:-1], 1, np.where(~above[1:] & above[:-1], -1, 0))
    sig[: 2 * length] = 0
    return sig


# --- Loxx: STD-Filtered, N-Pole Gaussian Filter (periyot 25, 5 kutup, std filtresi 10/1) ---
def gaussian_npole(close: pd.Series, period: int = 25, poles: int = 5, std_len: int = 10, std_k: float = 1.0) -> np.ndarray:
    c = close.to_numpy(float)
    beta = (1 - math.cos(2 * math.pi / period)) / (2 ** (1 / poles) - 1)
    alpha = -beta + math.sqrt(beta * beta + 2 * beta)
    f = c.copy()
    for _ in range(poles):  # N kutup = N kez art arda tek kutuplu süzgeç
        f = pd.Series(f).ewm(alpha=alpha, adjust=False).mean().to_numpy()
    # Std filtresi: değişim, değişimlerin std'sinin k katından küçükse önceki değer korunur
    out = f.copy()
    d = pd.Series(f).diff()
    sd = d.rolling(std_len).std().to_numpy()
    for i in range(1, len(out)):
        if not np.isnan(sd[i]) and abs(f[i] - out[i - 1]) < std_k * sd[i]:
            out[i] = out[i - 1]
    slope = np.sign(np.diff(out, prepend=np.nan))
    # Eğim yön değiştirince sinyal (0 eğim önceki yönü korur)
    dirn = pd.Series(np.where(slope == 0, np.nan, slope)).ffill().to_numpy()
    sig = np.zeros(len(c), int)
    sig[1:] = np.where((dirn[1:] == 1) & (dirn[:-1] == -1), 1, np.where((dirn[1:] == -1) & (dirn[:-1] == 1), -1, 0))
    sig[: period * 3] = 0
    return sig


# --- Libertus: Relative Strength Index - Divergences (RSI 14, pivot 5/5, aralık 5-60) ---
def rsi_divergence(close: pd.Series, n: int = 14, lb_l: int = 5, lb_r: int = 5, rmin: int = 5, rmax: int = 60,
                   hidden: bool = False) -> np.ndarray:
    c = close.to_numpy(float)
    r = _rsi(pd.Series(c), n).to_numpy()
    _, rpl = _pivots(np.nan_to_num(r, nan=50), lb_l, lb_r)
    rph, _ = _pivots(np.nan_to_num(r, nan=50), lb_l, lb_r)
    sig = np.zeros(len(c), int)
    last_l = last_h = None  # (pivot mumu, rsi, fiyat)
    for i in range(len(c)):
        j = i - lb_r
        if not np.isnan(rpl[i]):
            cur = (j, r[j], c[j])
            if last_l and rmin <= j - last_l[0] <= rmax:
                bull = cur[1] > last_l[1] and cur[2] < last_l[2]          # klasik: fiyat düşük dip, RSI yüksek dip
                hbull = cur[1] < last_l[1] and cur[2] > last_l[2]         # gizli
                if (hbull if hidden else bull):
                    sig[i] = 1
            last_l = cur
        if not np.isnan(rph[i]):
            cur = (j, r[j], c[j])
            if last_h and rmin <= j - last_h[0] <= rmax:
                bear = cur[1] < last_h[1] and cur[2] > last_h[2]
                hbear = cur[1] > last_h[1] and cur[2] < last_h[2]
                if (hbear if hidden else bear):
                    sig[i] = -1
            last_h = cur
    return sig


# --- LonesomeTheBlue: Support Resistance Channels (basitleştirilmiş: pivot 10, geriye 290 mum) ---
def sr_channels(close: pd.Series, prd: int = 10, loopback: int = 290, width_pct: float = 5.0) -> np.ndarray:
    """Son `loopback` mumdaki pivotlardan, (290 mumluk aralığın %5'i genişlikte) en çok pivot içeren
    direnç/destek kanalını bulur; kapanış kanalın üstüne çıkınca Buy, altına inince Sell."""
    c = close.to_numpy(float)
    ph, pl = _pivots(c, prd, prd)
    piv = np.where(~np.isnan(ph), ph, pl)
    sig = np.zeros(len(c), int)
    for i in range(loopback, len(c)):
        lo, hi = c[i - loopback : i].min(), c[i - loopback : i].max()
        w = (hi - lo) * width_pct / 100
        pv = piv[i - loopback : i]
        pv = pv[~np.isnan(pv)]
        if len(pv) < 2 or w <= 0:
            continue
        # En yoğun kanal: her pivotun etrafında w genişlikteki pencerede kaç pivot var
        best = max(pv, key=lambda p: ((pv >= p) & (pv <= p + w)).sum())
        top, bot = best + w, best
        if c[i - 1] <= top < c[i]:
            sig[i] = 1
        elif c[i - 1] >= bot > c[i]:
            sig[i] = -1
    return sig


# --- Loxx: JCFBaux Volatility → yön vermez; diğer göstergelere oynaklık filtresi olarak ---
def vol_regime(close: pd.Series, n: int = 30, ref: int = 1440) -> np.ndarray:
    """1: oynaklık son günün medyanının üstünde, 0: altında (JCFBaux'un yaklaşık karşılığı)."""
    v = np.log(close).diff().abs().rolling(n).mean()
    return (v > v.rolling(ref, min_periods=300).median()).to_numpy().astype(int)


INDICATORS = {
    "UT Bot (QuantNomad) 1/10": lambda c: utbot.ut_bot(pd.DataFrame({"close": c}), 1, 10),
    "Trendlines w/ Breaks (LuxAlgo)": trendlines_breaks,
    "TRAMA (LuxAlgo)": trama,
    "Gaussian N-Pole (Loxx)": gaussian_npole,
    "RSI Divergence (Libertus)": rsi_divergence,
    "RSI Gizli Divergence (Libertus)": lambda c: rsi_divergence(c, hidden=True),
    "S/R Channels (LonesomeTheBlue)": sr_channels,
}


def _score(res: list[tuple[np.ndarray, float]]) -> dict:
    r = np.concatenate([x for x, _ in res]) if res else np.array([], np.int8)
    n, w = int((r != 0).sum()), int((r == 1).sum())
    if not n:
        return {"trades": 0, "win_rate": None, "be": None, "ev": None, "p": None}
    pnl = sum(float(((x == 1) * p - (x == -1)).sum()) for x, p in res)
    be = sum((1 / (1 + p)) * int((x != 0).sum()) for x, p in res) / n
    z = (w - n * be - 0.5) / math.sqrt(n * be * (1 - be))
    return {"trades": n, "win_rate": round(w / n * 100, 2), "be": round(be * 100, 2),
            "ev": round(pnl / n * 100, 2), "p": round(0.5 * math.erfc(z / math.sqrt(2)), 4)}


def evaluate(frames: dict[str, pd.DataFrame], payouts: dict[str, float], expiries=EXPIRIES, delays=(0, 1),
             with_vol_filter: bool = True) -> pd.DataFrame:
    rows = []
    for name, fn in INDICATORS.items():
        sigs = {p: np.asarray(fn(df["close"])) for p, df in frames.items()}
        regs = {p: vol_regime(df["close"]) for p, df in frames.items()} if with_vol_filter else {}
        variants = [("", None)] + ([("+yüksek oynaklık", 1), ("+düşük oynaklık", 0)] if with_vol_filter else [])
        for vname, keep in variants:
            for d in delays:
                for e in expiries:
                    res = []
                    for p, df in frames.items():
                        s = sigs[p] if keep is None else np.where(regs[p] == keep, sigs[p], 0)
                        res.append((backtest.trades(df, s, e, delay=d), payouts.get(p, 0.85)))
                    rows.append({"indicator": name + vname, "delay": d, "expiry": e, **_score(res)})
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pocket")
    ap.add_argument("--pickle", help="Önceden indirilmiş Yahoo verisi (utbot.yahoo_frames çıktısı)")
    ap.add_argument("--payout", type=float, default=0.85)
    a = ap.parse_args()
    if a.pocket:
        from . import pocket_log
        log = pocket_log.load(a.pocket)
        px = pocket_log.price_series(log)
        frames = {p: px[[p]].rename(columns={p: "close"}).dropna() for p in px.columns}
        payouts = pocket_log.payout_by_symbol(log)
        src = "Pocket'ın kendi fiyatları, gerçek ödemeler"
    else:
        import pickle
        frames = pickle.load(open(a.pickle, "rb")) if a.pickle else utbot.yahoo_frames()
        payouts = {p: a.payout for p in frames}
        src = f"Yahoo 1 dk, {len(frames)} parite, ödeme %{a.payout * 100:.0f}"
    r = evaluate(frames, payouts)
    alpha = 0.05 / len(r)
    print(f"TradingView göstergeleri — {src}; {len(r)} test, Bonferroni eşiği p < {alpha:.5f}\n")
    base = r[~r.indicator.str.contains(r"\+")]
    print(base.to_string(index=False))
    print("\nOynaklık filtresi (JCFBaux yerine) ile en iyi 8 (en az 100 işlem):")
    f = r[r.indicator.str.contains(r"\+") & (r.trades >= 100)].sort_values("win_rate", ascending=False).head(8)
    print(f.to_string(index=False))
    print(f"\nEşiği geçen: {int((r.p < alpha).sum())}")


if __name__ == "__main__":
    main()
