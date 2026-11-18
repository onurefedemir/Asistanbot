"""2. tur: 1. turda elenen tüm stratejilerin yerine hiç denenmemiş aileler.

Yeni aileler:
- lead_lag:        Bir çiftin "kardeşleri" (aynı para birimini paylaşan çiftler) hareket ettiği
                   halde kendisi geride kaldıysa, aradaki farkı kapatacağı yöne işlem.
- triangle:        EURGBP'nin EURUSD/GBPUSD'den hesaplanan "olması gereken" değerinden sapması;
                   sapmanın kapanacağı yöne işlem (aynı mantık EURJPY, GBPJPY için).
- usd_basket:      Doların genel yönü (sepet) ile tek çiftin ayrışması.
- seasonality:     Saat × dakika bazında eğitim döneminde görülen yön eğilimi (veri madenciliği;
                   test dönemi gerçek olup olmadığını gösterir).
- breakout:        Son n dakikanın tepesini/dibini kırma (momentum) ve kırılımın geri dönmesi.
- mtf_pullback:    5 dk'lık trend yönünde, 1 dk'lık aşırı geri çekilmede işlem.
- vol_filtered:    Yalnızca düşük/yüksek oynaklık rejiminde ortalamaya dönüş.

Tümü gerçekçi girişle (1 dk gecikme) ve 1. turla aynı eğitim/test ayrımıyla sınanır.
"""

from __future__ import annotations

import argparse
import itertools
import json

import numpy as np
import pandas as pd

from . import backtest, data
from .strategies import _rsi

EXPIRIES = [1, 2, 3, 5]


def aligned(db: str) -> pd.DataFrame:
    """Tüm çiftlerin kapanışlarını ortak dakika ızgarasında birleştirir (eksikler NaN)."""
    closes = {}
    for p in data.PAIRS:
        df = data.load(p, db)
        if len(df) > 5000:
            closes[p] = df["close"]
    return pd.DataFrame(closes).sort_index()


# Her çiftin taban/karşıt para birimine göre USD'ye karşı yönü
USD_SIDE = {"EURUSD": 1, "GBPUSD": 1, "AUDUSD": 1, "USDJPY": -1, "USDCAD": -1, "USDCHF": -1}
SIBLINGS = {
    "EURUSD": [("GBPUSD", 1), ("AUDUSD", 1), ("USDCHF", -1)],
    "GBPUSD": [("EURUSD", 1), ("AUDUSD", 1), ("USDCHF", -1)],
    "AUDUSD": [("EURUSD", 1), ("GBPUSD", 1), ("USDCAD", -1)],
    "USDJPY": [("EURJPY", 1), ("GBPJPY", 1)],
    "USDCAD": [("USDCHF", 1), ("AUDUSD", -1), ("AUDCAD", -1)],
    "USDCHF": [("USDCAD", 1), ("EURUSD", -1), ("GBPUSD", -1)],
    "EURJPY": [("GBPJPY", 1), ("USDJPY", 1)],
    "GBPJPY": [("EURJPY", 1), ("USDJPY", 1)],
    "EURGBP": [("EURUSD", 1), ("GBPUSD", -1)],
    "AUDCAD": [("AUDUSD", 1), ("USDCAD", 1)],
}
TRIANGLES = {  # çift: (a, b, işlem) → çift ≈ a / b  veya a * b
    "EURGBP": ("EURUSD", "GBPUSD", "div"),
    "EURJPY": ("EURUSD", "USDJPY", "mul"),
    "GBPJPY": ("GBPUSD", "USDJPY", "mul"),
    "AUDCAD": ("AUDUSD", "USDCAD", "mul"),
}


def _z(x: pd.Series, n: int) -> pd.Series:
    return (x - x.rolling(n).mean()) / x.rolling(n).std()


def _vol(c: pd.Series) -> pd.Series:
    return np.log(c).diff().rolling(60).std()


def lead_lag(px: pd.DataFrame, pair: str, k: int, z: float) -> np.ndarray:
    lr = np.log(px.ffill(limit=2)).diff(k)
    sib = pd.concat([s * lr[p] for p, s in SIBLINGS[pair] if p in px], axis=1).mean(axis=1)  # eksikleri atlar
    gap = (sib - lr[pair]) / (_vol(px[pair]) * np.sqrt(k))
    return np.where(gap > z, 1, np.where(gap < -z, -1, 0))


def triangle(px: pd.DataFrame, pair: str, n: int, z: float) -> np.ndarray:
    if pair not in TRIANGLES:
        return np.zeros(len(px), int)
    a, b, op = TRIANGLES[pair]
    pf = px.ffill(limit=2)
    implied = pf[a] / pf[b] if op == "div" else pf[a] * pf[b]
    dev = _z(np.log(px[pair]) - np.log(implied), n)
    return np.where(dev < -z, 1, np.where(dev > z, -1, 0))


def usd_basket(px: pd.DataFrame, pair: str, k: int, z: float) -> np.ndarray:
    if pair not in USD_SIDE:
        return np.zeros(len(px), int)
    lr = np.log(px.ffill(limit=2)).diff(k)
    basket = pd.concat([-s * lr[p] for p, s in USD_SIDE.items() if p in px and p != pair], axis=1).mean(axis=1)
    # USD güçlendi ama bu çift buna uymadıysa, uyum yönünde
    expected = -USD_SIDE[pair] * basket
    gap = (expected - lr[pair]) / (_vol(px[pair]) * np.sqrt(k))
    return np.where(gap > z, 1, np.where(gap < -z, -1, 0))


def breakout(px, pair, n, mode):
    c = px[pair]
    hi, lo = c.shift(1).rolling(n).max(), c.shift(1).rolling(n).min()
    s = np.where(c > hi, 1, np.where(c < lo, -1, 0))
    return s if mode == "mom" else -s


def mtf_pullback(px, pair, slow, rsi_n):
    c = px[pair]
    c5 = c.resample("5min").last().reindex(c.index, method="ffill").shift(5)  # yalnızca kapanmış 5 dk mumları
    trend = c5 - c5.rolling(slow).mean()
    r = _rsi(c, rsi_n)
    return np.where((trend > 0) & (r < 25), 1, np.where((trend < 0) & (r > 75), -1, 0))


def vol_filtered(px, pair, regime, z):
    c = px[pair]
    v = _vol(c)
    vr = v / v.rolling(1440, min_periods=300).median()
    zz = _z(c, 20)
    sig = np.where(zz < -z, 1, np.where(zz > z, -1, 0))
    keep = (vr < 0.8) if regime == "low" else (vr > 1.3)
    return np.where(keep, sig, 0)


GRID = {
    "lead_lag": (lead_lag, {"k": [1, 2, 3, 5], "z": [1.0, 1.5, 2.0, 2.5]}),
    "triangle": (triangle, {"n": [20, 60, 240], "z": [1.5, 2.0, 2.5]}),
    "usd_basket": (usd_basket, {"k": [1, 3, 5, 15], "z": [1.0, 1.5, 2.0]}),
    "breakout": (breakout, {"n": [15, 30, 60, 120], "mode": ["mom", "rev"]}),
    "mtf_pullback": (mtf_pullback, {"slow": [6, 12, 24], "rsi_n": [3, 5]}),
    "vol_filtered": (vol_filtered, {"regime": ["low", "high"], "z": [2.0, 2.5]}),
}


LONG_GRID = {
    "lead_lag": {"k": [15, 30], "z": [1.0, 1.5, 2.0]},
    "triangle": {"n": [480, 960], "z": [1.5, 2.0, 2.5]},
    "usd_basket": {"k": [30, 60], "z": [1.0, 1.5, 2.0]},
    "breakout": {"n": [240, 480], "mode": ["mom", "rev"]},
    "mtf_pullback": {"slow": [48, 96], "rsi_n": [14]},
}


def seasonality_signals(px: pd.DataFrame, pair: str, cut, expiry: int, min_obs: int, bias: float):
    """Eğitim döneminde (saat, dakika) hücresine göre yön eğilimi öğrenir; tüm döneme uygular."""
    c = px[pair]
    fut = np.sign(c.shift(-(expiry + 1)) - c.shift(-1))  # gecikme 1 ile aynı hedef
    key = c.index.hour * 60 + c.index.minute
    train = (c.index < cut) & fut.notna() & (fut != 0)
    g = pd.DataFrame({"k": key[train], "y": (fut[train] > 0).astype(float)}).groupby("k")["y"].agg(["mean", "count"])
    g = g[g["count"] >= min_obs]
    up = set(g.index[g["mean"] >= 0.5 + bias])
    dn = set(g.index[g["mean"] <= 0.5 - bias])
    k = np.asarray(key)
    return np.where(np.isin(k, list(up)), 1, np.where(np.isin(k, list(dn)), -1, 0))


def run(db: str, payout: float = 0.85, train_frac: float = 0.7, min_trades: int = 200, per_family: int = 2) -> dict:
    px = aligned(db)
    cut = px.index[int(len(px) * train_frac)]
    configs = []
    spaces = [(n, fn, sp) for n, (fn, sp) in GRID.items()]
    if max(EXPIRIES) >= 15:
        spaces += [(n, GRID[n][0], sp) for n, sp in LONG_GRID.items()]
    for name, fn, space in spaces:
        for vals in itertools.product(*space.values()):
            configs.append((name, dict(zip(space, vals)), fn))
    for e in EXPIRIES:
        for min_obs, b in itertools.product([10, 15], [0.15, 0.2]):
            configs.append(("seasonality", {"expiry": e, "min_obs": min_obs, "bias": b}, None))

    rows = []
    for name, params, fn in configs:
        per_exp = {e: {"train": [], "test": []} for e in EXPIRIES}
        for pair in px.columns:
            df = px[[pair]].rename(columns={pair: "close"}).dropna()
            if name == "seasonality":
                sig_full = seasonality_signals(px, pair, cut, **params)
            else:
                sig_full = np.asarray(fn(px, pair, **params))
            sig = pd.Series(sig_full, index=px.index).reindex(df.index).fillna(0).to_numpy()
            exps = [params["expiry"]] if name == "seasonality" else EXPIRIES
            for e in exps:
                for part, m in (("train", df.index < cut), ("test", df.index >= cut)):
                    per_exp[e][part].append(backtest.trades(df[m], sig[m], e, delay=1))
        for e, parts in per_exp.items():
            if not parts["train"]:
                continue
            tr = backtest.stats(np.concatenate(parts["train"]), payout)
            te = backtest.stats(np.concatenate(parts["test"]), payout)
            rows.append({"strategy": name, "params": params, "expiry": e, "train": tr, "test": te})

    # Her aileden eğitimde en iyi `per_family` aday; tek bir aile listeyi doldurmasın
    best = []
    for fam in dict.fromkeys(r["strategy"] for r in rows):
        el = [r for r in rows if r["strategy"] == fam and r["train"]["trades"] >= min_trades]
        best += sorted(el, key=lambda r: r["train"]["win_rate"], reverse=True)[:per_family]
    alpha = 0.05 / max(len(best), 1)
    for r in best:
        r["passes"] = bool(r["test"]["trades"] >= 60 and r["test"]["p_value"] is not None
                           and r["test"]["p_value"] < alpha)
    fams = {}
    for r in rows:
        f = fams.setdefault(r["strategy"], {"configs": 0, "best_test": 0, "best_test_n": 0})
        f["configs"] += 1
        if r["test"]["trades"] >= 100 and (r["test"]["win_rate"] or 0) > f["best_test"]:
            f["best_test"], f["best_test_n"] = r["test"]["win_rate"], r["test"]["trades"]
    return {"cut": str(cut), "combinations_tested": len(rows), "alpha": alpha, "best": best, "families": fams,
            "breakeven": round(backtest.breakeven(payout) * 100, 2)}


def report(r: dict) -> str:
    out = [f"2. tur — eğitim/test kesimi {r['cut'][:16]}, giriş gecikmesi 1 dk, başa baş %{r['breakeven']}",
           f"Denenen kombinasyon: {r['combinations_tested']}", "",
           f"{'strateji':<14}{'parametre':<38}{'vade':>5} | {'eğitim':>15} | {'test':>15} {'p':>7}  geçti"]
    for b in r["best"]:
        tr, te = b["train"], b["test"]
        ps = ",".join(f"{k}={v}" for k, v in b["params"].items() if k != "expiry")
        out.append(f"{b['strategy']:<14}{ps:<38}{b['expiry']:>4}d | %{tr['win_rate']:>5} n={tr['trades']:<6} | "
                   f"%{te['win_rate']!s:>5} n={te['trades']:<6} {te['p_value']!s:>7}  {'EVET' if b['passes'] else 'hayır'}")
    out += ["", "Aile bazında test döneminin en iyisi (en az 100 işlem):"]
    for f, v in r["families"].items():
        out.append(f"  {f:<14} {v['configs']:>4} kombinasyon, en iyi test %{v['best_test']} (n={v['best_test_n']})")
    out.append(f"\nTesti geçen: {sum(b['passes'] for b in r['best'])} / {len(r['best'])} (eşik p < {r['alpha']:.4f})")
    return "\n".join(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=data.DB)
    ap.add_argument("--payout", type=float, default=0.85)
    ap.add_argument("--json")
    ap.add_argument("--expiries", type=int, nargs="*", help="Vadeler (dk), ör. --expiries 15 30")
    a = ap.parse_args()
    if a.expiries:
        EXPIRIES[:] = a.expiries
    res = run(a.db, a.payout)
    print(report(res))
    if a.json:
        with open(a.json, "w") as f:
            json.dump(res, f, ensure_ascii=False, indent=1, default=str)
