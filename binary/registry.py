"""Ön kayıtlı adayların ileri doğrulaması.

Keşifte iyi görünen bir aday, parametreleri dondurularak `candidates.json`'a tarihle yazılır.
Bir aday ancak KAYIT TARİHİNDEN SONRA oluşan, hiç görülmemiş veride geçerse "geçti" sayılır.
Böylece "testi geçene kadar dene" yaklaşımının yarattığı şans sonuçları elenir.

Kullanım:  python -m binary.registry            (Yahoo'dan son 60 gün 5 dk veriyi çeker)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from . import backtest, data, round3

FILE = Path(__file__).with_name("candidates.json")
MIN_TRADES = 300
P_PASS = 0.01


def load() -> list[dict]:
    return json.loads(FILE.read_text(encoding="utf-8"))


def validate(px: pd.DataFrame, cand: dict) -> dict:
    px = px[px.index.as_unit("s").asi8 % cand["bar_sec"] == 0]
    start = pd.Timestamp(cand["registered_at"], tz="UTC") + pd.Timedelta(days=1)  # kayıt gününün tamamı hariç
    out = {"id": cand["id"], "registered_at": cand["registered_at"], "data_until": str(px.index.max())[:16]}
    for pay in (0.85, 0.75):
        r = round3.evaluate(px, payout=pay, train_days=cand["train_days"], bar_sec=cand["bar_sec"],
                            expiries=[cand["expiry_bars"]], thresholds=[cand["threshold"]], test_from=start)
        s = r.iloc[0].to_dict() if len(r) else {"trades": 0, "win_rate": None, "breakeven": round(backtest.breakeven(pay) * 100, 2), "p_value": None}
        out[f"payout_{int(pay * 100)}"] = {k: s.get(k) for k in ("trades", "win_rate", "breakeven", "ev_per_trade", "p_value")}
    s85 = out["payout_85"]
    if (s85["trades"] or 0) < MIN_TRADES:
        out["status"] = f"BEKLİYOR ({s85['trades'] or 0}/{MIN_TRADES} işlem)"
    elif s85["p_value"] is not None and s85["p_value"] < P_PASS:
        out["status"] = "GEÇTİ (%85 ödemede)"
    else:
        out["status"] = "KALDI"
    return out


def report(results: list[dict]) -> str:
    lines = ["Ön kayıtlı adayların ileri doğrulaması (yalnızca kayıt tarihinden sonraki veri)", ""]
    for r in results:
        lines.append(f"{r['id']}  kayıt {r['registered_at']}  veri {r['data_until']} UTC'ye kadar  →  {r['status']}")
        for k in ("payout_85", "payout_75"):
            s = r[k]
            lines.append(f"  ödeme %{k[-2:]}: {s['trades']} işlem, isabet %{s['win_rate']}, başa baş %{s['breakeven']}, "
                         f"işlem başı %{s.get('ev_per_trade')}, p={s['p_value']}")
    lines += ["", f"Geçme kuralı: en az {MIN_TRADES} işlem ve %85 ödemede p < {P_PASS}. "
              "Geçse bile önce demo hesapta doğrulanmalı; %75 ödemede de kâr gerekir."]
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pickle", help="Önceden indirilmiş 5 dk veri (test için)")
    a = ap.parse_args()
    px = pd.read_pickle(a.pickle) if a.pickle else data.aligned_range(data.PAIRS, "5m", "60d")
    print(report([validate(px, c) for c in load()]))
