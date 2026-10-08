"""Twelve Data spot enrichment and Futures-to-CFD level conversion."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import requests

from .price_memory import build_price_memory

API_URL = "https://api.twelvedata.com/time_series"
DEFAULT_SYMBOL = "XAU/USD"
DEFAULT_MAX_AGE_SECONDS = 600


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


class TwelveDataError(RuntimeError):
    pass


def fetch_spot(symbol: str | None = None, api_key: str | None = None) -> dict[str, Any]:
    key = api_key or os.environ.get("TWELVEDATA_API_KEY", "")
    if not key:
        raise TwelveDataError("TWELVEDATA_API_KEY ไม่ได้ตั้งค่า")
    params = {
        "symbol": symbol or os.environ.get("TWELVEDATA_SYMBOL", DEFAULT_SYMBOL),
        "interval": "1min",
        "outputsize": 1,
        "timezone": "UTC",
        "apikey": key,
    }
    try:
        response = requests.get(API_URL, params=params, timeout=20)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise TwelveDataError(f"เรียก Twelve Data ไม่สำเร็จ: {exc}") from exc
    if data.get("status") == "error" or data.get("code"):
        raise TwelveDataError(data.get("message") or str(data))
    values = data.get("values") or []
    if not values:
        raise TwelveDataError("Twelve Data ไม่คืนค่า spot")
    latest = values[0]
    try:
        spot = float(latest["close"])
    except (KeyError, TypeError, ValueError) as exc:
        raise TwelveDataError(f"ค่า close จาก Twelve Data ไม่ถูกต้อง: {latest}") from exc

    timestamp_raw = latest.get("datetime")
    timestamp = _parse_timestamp(timestamp_raw)
    if timestamp is None:
        raise TwelveDataError(f"Twelve Data คืน timestamp ไม่ถูกต้อง: {timestamp_raw}")

    now = datetime.now(timezone.utc)
    age_seconds = (now - timestamp).total_seconds()
    max_age = max(30, int(os.environ.get("TWELVEDATA_MAX_AGE_SECONDS", str(DEFAULT_MAX_AGE_SECONDS))))
    if age_seconds < -30:
        raise TwelveDataError(f"Twelve Data timestamp อยู่ในอนาคต {abs(age_seconds):.0f}s")
    if age_seconds > max_age:
        raise TwelveDataError(f"Twelve Data spot stale: age={age_seconds:.0f}s > max={max_age}s")

    return {
        "symbol": params["symbol"],
        "spot_price": spot,
        "timestamp": timestamp.isoformat(),
        "age_seconds": round(max(0.0, age_seconds), 1),
        "max_age_seconds": max_age,
        "interval": "1min",
        "source": "twelve_data",
    }


def _convert(value: Any, diff: float) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value) - diff, 5)
    except (TypeError, ValueError):
        return None


def enrich_with_basis(parsed: dict, spot_data: dict) -> dict:
    """Add spot/basis and CFD equivalents while preserving CME Futures levels."""
    futures = parsed.get("future_price")
    spot = spot_data.get("spot_price")
    if futures is None or spot is None:
        raise TwelveDataError("ขาด future_price หรือ spot_price สำหรับคำนวณ diff")
    futures = float(futures)
    spot = float(spot)
    diff = round(futures - spot, 5)

    parsed["spot_price"] = spot
    parsed["basis_diff"] = diff
    parsed["cfd_price"] = spot
    parsed["price_conversion"] = {
        "formula": "CFD = Futures level - (Futures price - Spot price)",
        "futures_price": futures,
        "spot_price": spot,
        "diff": diff,
        "cfd_price": spot,
        "source": spot_data,
        "source_name": "twelve_data",
        "source_symbol": spot_data.get("symbol") or os.environ.get("TWELVEDATA_SYMBOL", DEFAULT_SYMBOL),
        "source_timestamp": spot_data.get("timestamp"),
        "source_age_seconds": spot_data.get("age_seconds"),
    }

    raw = parsed.get("raw_series")
    if not isinstance(raw, dict):
        return parsed

    rows = raw.get("strike_rows") or []
    for row in rows:
        row["strike_cfd"] = _convert(row.get("strike"), diff)
    for item in raw.get("expected_ranges") or []:
        item["lower_cfd"] = _convert(item.get("lower"), diff)
        item["upper_cfd"] = _convert(item.get("upper"), diff)
    for marker in raw.get("delta_markers") or []:
        marker["strike_cfd"] = _convert(marker.get("strike"), diff)
    raw["cfd_conversion"] = parsed["price_conversion"]
    raw["cfd_strike_rows"] = [
        {
            "strike_cfd": row.get("strike_cfd"),
            "oiPut": row.get("oiPut"),
            "oiCall": row.get("oiCall"),
            "oiTotal": row.get("oiTotal"),
            "ivolumePut": row.get("ivolumePut"),
            "ivolumeCall": row.get("ivolumeCall"),
        }
        for row in rows
    ]
    raw["cfd_expected_ranges"] = [
        {
            "title": item.get("title"),
            "lower_cfd": item.get("lower_cfd"),
            "upper_cfd": item.get("upper_cfd"),
            "percent": item.get("percent"),
        }
        for item in raw.get("expected_ranges") or []
    ]
    return parsed
