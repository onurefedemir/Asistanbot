"""İkili opsiyon kurallarıyla backtest.

- Giriş: sinyal mumunun kapanışı (pratikte bir sonraki dakikanın başında tıklanır).
- Sonuç: `expiry` dakika sonraki kapanış. CALL için yukarıdaysa kazanç, eşitse iade.
- Bir çiftte işlem açıkken yeni işlem açılmaz (örtüşen işlemler istatistiği şişirir).
- Veri boşluğu (hafta sonu vb.) olan işlemler atlanır.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


def breakeven(payout: float) -> float:
    """Kazançta stake'in `payout` katı kazanılıyorsa başa baş kazanma oranı."""
    return 1 / (1 + payout)


def trades(
    df: pd.DataFrame, signal: np.ndarray, expiry: int, hours: set[int] | None = None, delay: int = 0,
    bar_sec: int = 60,
) -> np.ndarray:
    """Her işlem için +1 (kazanç), -1 (kayıp), 0 (iade) dizisi döndürür.

    delay: sinyalden kaç mum sonra girileceği. delay=0 sinyal mumunun kapanışından
    girer (iyimser); delay=1 bir dakika sonraki kapanıştan girer. Kazanç delay=1'de
    kayboluyorsa, kaynağı verideki tek mumluk gürültüdür ve gerçekte alınamaz.
    bar_sec: mum süresi (sn). expiry ve delay mum sayısıdır (1 dk mumda dakika).
    """
    c = df["close"].to_numpy()
    ts = df.index.as_unit("s").asi8.astype(np.int64)
    n = len(c)
    span = expiry + delay
    sig = np.asarray(signal)[: n - span]
    ok = (sig != 0) & (ts[span:] - ts[: n - span] == span * bar_sec)
    if hours is not None:
        ok &= np.isin(df.index.hour.to_numpy()[: n - span], list(hours))
    idx = np.flatnonzero(ok)
    if not len(idx):
        return np.array([], dtype=np.int8)
    # Örtüşmeyen işlemler: bir işlem açıkken gelen sinyaller atlanır
    keep = []
    next_free = -1
    for i in idx:
        if i >= next_free:
            keep.append(i)
            next_free = i + span
    keep = np.array(keep)
    diff = (c[keep + span] - c[keep + delay]) * sig[keep]
    return np.sign(diff).astype(np.int8)


def stats(results: np.ndarray, payout: float = 0.85) -> dict:
    wins = int((results == 1).sum())
    losses = int((results == -1).sum())
    ties = int((results == 0).sum())
    n = wins + losses
    be = breakeven(payout)
    wr = wins / n if n else float("nan")
    # Tek yönlü z testi: kazanma oranı başa baştan anlamlı şekilde büyük mü?
    z = (wins - n * be - 0.5) / math.sqrt(n * be * (1 - be)) if n else float("nan")
    p = 0.5 * math.erfc(z / math.sqrt(2)) if n else float("nan")
    return {
        "trades": n,
        "ties": ties,
        "win_rate": round(wr * 100, 2) if n else None,
        "breakeven": round(be * 100, 2),
        "edge": round((wr - be) * 100, 2) if n else None,
        # Stake başına beklenen getiri (%)
        "ev_per_trade": round((wr * payout - (1 - wr)) * 100, 2) if n else None,
        "p_value": round(p, 4) if n else None,
    }
