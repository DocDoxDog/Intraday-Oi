"""Deterministic XAU/USD technical context for analysis, not display."""
from __future__ import annotations
import os
import requests

API_URL = "https://api.twelvedata.com/time_series"


def _ema(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    value = sum(values[:period]) / period
    for price in values[period:]:
        value = price * k + value * (1 - k)
    return round(value, 5)


def _fetch(symbol: str, interval: str, key: str, outputsize: int = 250) -> list[dict]:
    r = requests.get(API_URL, params={
        "symbol": symbol, "interval": interval, "outputsize": outputsize,
        "timezone": "UTC", "apikey": key,
    }, timeout=25)
    r.raise_for_status()
    data = r.json()
    if data.get("status") == "error" or data.get("code"):
        raise RuntimeError(data.get("message") or str(data))
    values = list(reversed(data.get("values") or []))
    out = []
    for x in values:
        try:
            out.append({k: float(x[k]) for k in ("open", "high", "low", "close")}|{"datetime": x.get("datetime")})
        except (KeyError, TypeError, ValueError):
            continue
    if not out:
        raise RuntimeError(f"ไม่มี OHLC สำหรับ {symbol} {interval}")
    return out


def _structure(candles: list[dict]) -> dict:
    highs = [x["high"] for x in candles]
    lows = [x["low"] for x in candles]
    closes = [x["close"] for x in candles]
    last = candles[-1]
    ema50 = _ema(closes, 50)
    ema200 = _ema(closes, 200)
    previous = candles[-2] if len(candles) > 1 else last
    trend = "neutral"
    if ema50 is not None and ema200 is not None:
        if last["close"] > ema50 > ema200:
            trend = "bullish"
        elif last["close"] < ema50 < ema200:
            trend = "bearish"
    lookback = candles[-21:-1] if len(candles) > 21 else candles[:-1]
    prior_high = max((x["high"] for x in lookback), default=last["high"])
    prior_low = min((x["low"] for x in lookback), default=last["low"])
    sweep = "none"
    if last["high"] > prior_high and last["close"] < prior_high:
        sweep = "buy_side_sweep"
    elif last["low"] < prior_low and last["close"] > prior_low:
        sweep = "sell_side_sweep"
    bos = "none"
    if last["close"] > prior_high:
        bos = "bullish_bos"
    elif last["close"] < prior_low:
        bos = "bearish_bos"
    # Three-candle fair-value gap, using the latest completed candles.
    fvg = None
    if len(candles) >= 3:
        a, _, c = candles[-3:]
        if a["high"] < c["low"]:
            fvg = {"side": "bullish", "low": a["high"], "high": c["low"]}
        elif a["low"] > c["high"]:
            fvg = {"side": "bearish", "low": c["high"], "high": a["low"]}
    swing_high = max(highs[-50:])
    swing_low = min(lows[-50:])
    span = swing_high - swing_low
    fib = {
        "swing_high": round(swing_high, 5), "swing_low": round(swing_low, 5),
        "retracement_62": round(swing_high - span * 0.62, 5),
        "retracement_79": round(swing_high - span * 0.79, 5),
    }
    return {
        "timestamp": last.get("datetime"), "close": last["close"],
        "ema50": ema50, "ema200": ema200, "trend": trend,
        "sweep": sweep, "bos": bos, "fvg": fvg, "fibonacci": fib,
        "previous_close": previous["close"], "prior_high": prior_high, "prior_low": prior_low,
    }


def build_context(api_key: str | None = None, symbol: str | None = None) -> dict:
    key = api_key or os.environ.get("TWELVEDATA_API_KEY", "")
    if not key:
        raise RuntimeError("TWELVEDATA_API_KEY ไม่ได้ตั้งค่า")
    symbol = symbol or os.environ.get("TWELVEDATA_SYMBOL", "XAU/USD")
    intervals = {name: interval for name, interval in {
        "h4": "4h", "h1": "1h", "m15": "15min", "m5": "5min", "m1": "1min"
    }.items()}
    result = {"source": "twelve_data", "symbol": symbol, "timeframes": {}}
    for name, interval in intervals.items():
        candles = _fetch(symbol, interval, key)
        result["timeframes"][name] = _structure(candles)
    h4, h1 = result["timeframes"]["h4"], result["timeframes"]["h1"]
    result["confirmation"] = {
        "htf_aligned": h4["trend"] != "neutral" and h4["trend"] == h1["trend"],
        "bias": h4["trend"] if h4["trend"] == h1["trend"] else "mixed",
        "m15_m5_aligned": result["timeframes"]["m15"]["trend"] == result["timeframes"]["m5"]["trend"],
    }
    return result
