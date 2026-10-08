"""Deterministic XAU/USD technical context for the analyst.
All derived metrics are explicit and remain UNKNOWN when source data is missing.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
import requests

from src.auction import build_auction_profile

API_URL = "https://api.twelvedata.com/time_series"
BANGKOK_TZ = timezone(timedelta(hours=7))


def _num(value):
    try:
        return None if value is None or value == "" else float(value)
    except (TypeError, ValueError):
        return None


def _parse_dt(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BANGKOK_TZ)


def _ema(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    value = sum(values[:period]) / period
    for price in values[period:]:
        value = price * k + value * (1 - k)
    return round(value, 5)


def _atr(candles: list[dict], period: int = 14) -> float | None:
    if len(candles) < period + 1:
        return None
    true_ranges = []
    for previous, current in zip(candles[-period-1:-1], candles[-period:]):
        true_ranges.append(
            max(
                current["high"] - current["low"],
                abs(current["high"] - previous["close"]),
                abs(current["low"] - previous["close"]),
            )
        )
    return round(sum(true_ranges) / period, 5)


def _session_vwap(candles: list[dict]) -> float | None:
    if not candles:
        return None
    last_dt = _parse_dt(candles[-1].get("datetime"))
    if last_dt is None:
        return None
    day = last_dt.date()
    selected = [x for x in candles if (_parse_dt(x.get("datetime")) or last_dt).date() == day]
    if not selected or any(_num(x.get("volume")) is None or _num(x.get("volume")) <= 0 for x in selected):
        return None
    total_volume = sum(_num(x["volume"]) or 0 for x in selected)
    if total_volume <= 0:
        return None
    weighted = sum(
        ((x["high"] + x["low"] + x["close"]) / 3.0) * (_num(x["volume"]) or 0)
        for x in selected
    )
    return round(weighted / total_volume, 5)


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

    fvg = None
    if len(candles) >= 3:
        a, _, c = candles[-3:]
        if a["high"] < c["low"]:
            fvg = {"side": "bullish", "low": a["high"], "high": c["low"]}
        elif a["low"] > c["high"]:
            fvg = {"side": "bearish", "low": c["high"], "high": a["low"]}

    swing_high = max(highs[-50:]) if highs else None
    swing_low = min(lows[-50:]) if lows else None
    span = (swing_high - swing_low) if swing_high is not None and swing_low is not None else None
    fib = {
        "swing_high": round(swing_high, 5) if swing_high is not None else None,
        "swing_low": round(swing_low, 5) if swing_low is not None else None,
        "retracement_62": round(swing_high - span * 0.62, 5) if span is not None else None,
        "retracement_79": round(swing_high - span * 0.79, 5) if span is not None else None,
    }

    momentum_5 = round(last["close"] - closes[-6], 5) if len(closes) >= 6 else None
    momentum_pct_5 = round((last["close"] / closes[-6] - 1) * 100, 5) if len(closes) >= 6 and closes[-6] else None

    return {
        "timestamp": last.get("datetime"),
        "close": last["close"],
        "ema50": ema50,
        "ema200": ema200,
        "trend": trend,
        "sweep": sweep,
        "bos": bos,
        "fvg": fvg,
        "fibonacci": fib,
        "previous_close": previous["close"],
        "prior_high": prior_high,
        "prior_low": prior_low,
        "atr14": _atr(candles, 14),
        "vwap": _session_vwap(candles),
        "latest_volume": _num(last.get("volume")),
        "volume_source_available": all(_num(x.get("volume")) is not None for x in candles),
        "momentum_5": momentum_5,
        "momentum_pct_5": momentum_pct_5,
    }


def _fetch(symbol: str, interval: str, key: str, outputsize: int = 250) -> list[dict]:
    r = requests.get(
        API_URL,
        params={
            "symbol": symbol,
            "interval": interval,
            "outputsize": outputsize,
            "timezone": "UTC",
            "apikey": key,
        },
        timeout=25,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("status") == "error" or data.get("code"):
        raise RuntimeError(data.get("message") or str(data))

    values = list(reversed(data.get("values") or []))
    out = []
    for x in values:
        try:
            item = {
                "open": float(x["open"]),
                "high": float(x["high"]),
                "low": float(x["low"]),
                "close": float(x["close"]),
                "datetime": x.get("datetime"),
            }
            volume = _num(x.get("volume"))
            if volume is not None:
                item["volume"] = volume
            out.append(item)
        except (KeyError, TypeError, ValueError):
            continue

    if not out:
        raise RuntimeError(f"ไม่มี OHLC สำหรับ {symbol} {interval}")
    return out


def build_context(api_key: str | None = None, symbol: str | None = None) -> dict:
    key = api_key or os.environ.get("TWELVEDATA_API_KEY", "")
    if not key:
        raise RuntimeError("TWELVEDATA_API_KEY ไม่ได้ตั้งค่า")
    symbol = symbol or os.environ.get("TWELVEDATA_SYMBOL", "XAU/USD")
    result = {"source": "twelve_data", "symbol": symbol, "timeframes": {}}
    candles_by_tf: dict[str, list[dict]] = {}
    for name, interval in {
        "h4": "4h",
        "h1": "1h",
        "m15": "15min",
        "m5": "5min",
        "m1": "1min",
    }.items():
        candles = _fetch(symbol, interval, key)
        candles_by_tf[name] = candles
        result["timeframes"][name] = _structure(candles)
        # Persistable source history: downstream engines can build price memory
        # and event outcomes without refetching or relying on derived summaries.
        result.setdefault("ohlcv", {})[name] = candles

    # OHLCV profile is intentionally labeled as a bar proxy. We do not claim
    # tick-level executed-volume precision without tick/order-book source data.
    try:
        result["auction"] = build_auction_profile(
            candles_by_tf.get("m5") or [],
            bin_size=float(os.environ.get("AUCTION_BIN_SIZE", "0.5")),
            value_area_pct=float(os.environ.get("AUCTION_VALUE_AREA_PCT", "0.70")),
        )
    except Exception as exc:
        result["auction"] = {
            "version": "auction-v1",
            "status": "UNKNOWN",
            "mode": "BAR_PROXY",
            "approximation": "CALENDAR_DAY_APPROX",
            "error": type(exc).__name__,
        }

    h4, h1 = result["timeframes"]["h4"], result["timeframes"]["h1"]
    result["confirmation"] = {
        "htf_aligned": h4["trend"] != "neutral" and h4["trend"] == h1["trend"],
        "bias": h4["trend"] if h4["trend"] == h1["trend"] else "mixed",
        "m15_m5_aligned": result["timeframes"]["m15"]["trend"] == result["timeframes"]["m5"]["trend"],
    }
    return result
