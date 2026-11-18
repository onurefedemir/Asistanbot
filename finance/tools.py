"""Ajanın çağırabildiği araçlar (custom tools): tanımlar + yerel çalıştırıcı.

Araçlar botun çalıştığı makinede çalışır; Claude yalnızca hangi aracı hangi
girdiyle çağıracağına karar verir.
"""

from __future__ import annotations

import json

from . import backtest, indicators, market
from .portfolio import Portfolio

_symbol = {"type": "string", "description": "Sembol. Kripto: BTCUSDT; BIST: THYAO.IS; ABD: AAPL; döviz: USDTRY=X"}
_interval = {"type": "string", "enum": list(market.INTERVALS), "description": "Mum aralığı (varsayılan 1d)"}

TOOL_DEFS = [
    {
        "type": "custom",
        "name": "get_price",
        "description": "Bir sembolün anlık/son fiyatını getirir.",
        "input_schema": {"type": "object", "properties": {"symbol": _symbol}, "required": ["symbol"]},
    },
    {
        "type": "custom",
        "name": "analyze_symbol",
        "description": (
            "Sembolün teknik analizini yapar: RSI, MACD, SMA20/50/200, Bollinger, ATR, volatilite, "
            "ATR tabanlı önerilen stop-loss/take-profit ve -5..+5 arası bir puan."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"symbol": _symbol, "interval": _interval},
            "required": ["symbol"],
        },
    },
    {
        "type": "custom",
        "name": "backtest_strategies",
        "description": (
            "Sembolün geçmiş verisinde hazır stratejileri (sma_cross, rsi_reversion, macd_trend, "
            "bollinger_reversion) komisyon dahil test eder; kazanma oranı, toplam getiri, "
            "al-tut karşılaştırması, max drawdown ve profit factor döndürür. Bir al/sat önerisinden "
            "önce mutlaka çağır."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": _symbol,
                "interval": _interval,
                "candles": {"type": "integer", "description": "Kaç mum (varsayılan 1000, en az 200)"},
            },
            "required": ["symbol"],
        },
    },
    {
        "type": "custom",
        "name": "get_portfolio",
        "description": "Kullanıcının sanal portföyünü (nakit, pozisyonlar, güncel değer, kâr/zarar, kazanma oranı) getirir.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "type": "custom",
        "name": "trade_history",
        "description": "Sanal portföydeki son işlemleri listeler.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "Varsayılan 20"}},
        },
    },
    {
        "type": "custom",
        "name": "paper_buy",
        "description": (
            "SANAL portföyde güncel piyasa fiyatından alım yapar (gerçek para değil). "
            "Yalnızca kullanıcı açıkça alım istediğinde ya da al/sat yetkisi verdiğinde kullan."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": _symbol,
                "amount": {"type": "number", "description": "Harcanacak nakit tutarı"},
                "reason": {"type": "string", "description": "İşlemin kısa gerekçesi"},
            },
            "required": ["symbol", "amount", "reason"],
        },
    },
    {
        "type": "custom",
        "name": "paper_sell",
        "description": (
            "SANAL portföyde güncel fiyattan satış yapar. fraction=1 tamamını satar. "
            "Yalnızca kullanıcı açıkça satış istediğinde ya da al/sat yetkisi verdiğinde kullan."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": _symbol,
                "fraction": {"type": "number", "description": "0-1 arası, varsayılan 1"},
                "reason": {"type": "string", "description": "İşlemin kısa gerekçesi"},
            },
            "required": ["symbol", "reason"],
        },
    },
]


def run_tool(name: str, args: dict, chat_id: int, portfolio: Portfolio) -> str:
    """Aracı çalıştırır, sonucu JSON metni olarak döndürür. Hataları da metin olarak döner."""
    try:
        result = _dispatch(name, args or {}, chat_id, portfolio)
    except Exception as e:  # ajan hatayı görüp başka yol deneyebilsin
        result = {"error": f"{type(e).__name__}: {e}"}
    return json.dumps(result, ensure_ascii=False, default=str)


def _dispatch(name: str, a: dict, chat_id: int, pf: Portfolio):
    if name == "get_price":
        return {"symbol": a["symbol"].upper(), "price": market.get_price(a["symbol"])}
    if name == "analyze_symbol":
        df = market.get_candles(a["symbol"], a.get("interval", "1d"), 400)
        return {"symbol": a["symbol"].upper(), "interval": a.get("interval", "1d"), **indicators.analyze(df)}
    if name == "backtest_strategies":
        n = max(200, int(a.get("candles", 1000)))
        df = market.get_candles(a["symbol"], a.get("interval", "1d"), n)
        return {"symbol": a["symbol"].upper(), "results": backtest.compare(df)}
    if name == "get_portfolio":
        s = pf.summary(chat_id)
        prices = {}
        for p in s["positions"]:
            try:
                prices[p["symbol"]] = market.get_price(p["symbol"])
            except Exception:
                pass
        return pf.summary(chat_id, prices)
    if name == "trade_history":
        return pf.history(chat_id, int(a.get("limit", 20)))
    if name == "paper_buy":
        price = market.get_price(a["symbol"])
        return pf.buy(chat_id, a["symbol"], price, float(a["amount"]), a.get("reason", ""))
    if name == "paper_sell":
        price = market.get_price(a["symbol"])
        return pf.sell(chat_id, a["symbol"], price, float(a.get("fraction", 1.0)), a.get("reason", ""))
    return {"error": f"Bilinmeyen araç: {name}"}
