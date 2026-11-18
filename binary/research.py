"""Strateji araştırması: tüm parametre ızgarasını eğitim döneminde dener, en iyileri
hiç görmediği test döneminde doğrular.

Kullanım:  python -m binary.research [--payout 0.85] [--db binary.db]

Neden iki dönem? Yüzlerce kombinasyon denendiğinde bazıları şans eseri iyi görünür.
Gerçek bir avantaj, test döneminde de başa baş oranının üstünde kalmalıdır.
"""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from . import backtest, data, strategies

EXPIRIES = [1, 2, 3, 5]
# UTC saatleri
SESSIONS = {
    "all": None,
    "asya": set(range(0, 7)),
    "londra": set(range(7, 12)),
    "ny_overlap": set(range(12, 17)),
}


def run(db: str, payout: float, delay: int = 1, train_frac: float = 0.7, min_trades: int = 300, top: int = 15):
    frames = {p: data.load(p, db) for p in data.PAIRS}
    frames = {p: df for p, df in frames.items() if len(df) > 5000}
    # Tüm çiftler için ortak zaman kesimi
    t_all = pd.concat([df.index.to_series() for df in frames.values()])
    cut = t_all.quantile(train_frac)
    period = {"train": (t_all.min(), cut), "test": (cut, t_all.max())}

    rows = []
    for name, fn, params in strategies.grid(long=max(EXPIRIES) >= 15):
        res = {(e, s, part): [] for e in EXPIRIES for s in SESSIONS for part in ("train", "test")}
        for df in frames.values():
            sig = np.asarray(fn(df["close"], **params))
            for part, sl in (("train", df.index < cut), ("test", df.index >= cut)):
                sub, ss = df[sl], sig[sl]
                for e in EXPIRIES:
                    for sname, hrs in SESSIONS.items():
                        res[(e, sname, part)].append(backtest.trades(sub, ss, e, hrs, delay))
        for e in EXPIRIES:
            for sname in SESSIONS:
                tr = backtest.stats(np.concatenate(res[(e, sname, "train")]), payout)
                te = backtest.stats(np.concatenate(res[(e, sname, "test")]), payout)
                rows.append({"strategy": name, "params": params, "expiry": e, "session": sname,
                             "train": tr, "test": te})

    tested = len(rows)
    eligible = [r for r in rows if r["train"]["trades"] >= min_trades]
    best = sorted(eligible, key=lambda r: r["train"]["win_rate"], reverse=True)[:top]
    # Test döneminde yalnızca seçilen `top` aday sınanır: Bonferroni eşiği 0.05/top
    alpha = 0.05 / top
    for r in best:
        r["passes"] = bool(
            r["test"]["trades"] >= min_trades * (1 - train_frac) / train_frac
            and r["test"]["p_value"] is not None and r["test"]["p_value"] < alpha
        )
    return {
        "pairs": {p: len(df) for p, df in frames.items()},
        "train_period": [str(x) for x in period["train"]],
        "test_period": [str(x) for x in period["test"]],
        "payout": payout,
        "delay": delay,
        "breakeven": round(backtest.breakeven(payout) * 100, 2),
        "combinations_tested": tested,
        "alpha": alpha,
        "best": best,
    }


def report(r: dict) -> str:
    out = [
        f"Veri: {sum(r['pairs'].values()):,} dakika, {len(r['pairs'])} çift",
        f"Eğitim: {r['train_period'][0][:16]} → {r['train_period'][1][:16]}",
        f"Test:   {r['test_period'][0][:16]} → {r['test_period'][1][:16]}",
        f"Ödeme %{r['payout']*100:.0f} → başa baş kazanma oranı %{r['breakeven']}",
        f"Giriş gecikmesi: {r['delay']} mum, vadeler: {', '.join(map(str, EXPIRIES))} dk",
        f"Denenen kombinasyon: {r['combinations_tested']}",
        "",
        f"{'strateji':<20}{'parametre':<28}{'vade':>5}{'seans':>11} | {'eğitim':>15} | {'test':>15} {'p':>7}  geçti",
    ]
    for b in r["best"]:
        tr, te = b["train"], b["test"]
        ps = ",".join(f"{k}={v}" for k, v in b["params"].items())
        out.append(
            f"{b['strategy']:<20}{ps:<28}{b['expiry']:>4}d{b['session']:>11} | "
            f"%{tr['win_rate']:>5} n={tr['trades']:<6} | %{te['win_rate']!s:>5} n={te['trades']:<6} "
            f"{te['p_value']!s:>7}  {'EVET' if b['passes'] else 'hayır'}"
        )
    n_pass = sum(b["passes"] for b in r["best"])
    out += ["", f"Testi geçen strateji: {n_pass} / {len(r['best'])} (eşik p < {r['alpha']:.4f})"]
    return "\n".join(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=data.DB)
    ap.add_argument("--payout", type=float, default=0.85)
    ap.add_argument("--delay", type=int, default=1,
                    help="Sinyalden sonra kaç mum beklenip girileceği. 0 iyimserdir: Yahoo verisindeki "
                         "tek mumluk gürültü sahte kazanç üretir (README'ye bakın).")
    ap.add_argument("--json", help="Sonuçları JSON olarak kaydet")
    ap.add_argument("--expiries", type=int, nargs="*", help="Vadeler (dk), ör. --expiries 15 30")
    a = ap.parse_args()
    if a.expiries:
        EXPIRIES[:] = a.expiries
    res = run(a.db, a.payout, a.delay)
    print(report(res))
    if a.json:
        with open(a.json, "w") as f:
            json.dump(res, f, ensure_ascii=False, indent=1, default=str)
