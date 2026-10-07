"""Canonical data-clock and provenance helpers."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any

REALTIME = "REALTIME"
INTRADAY_DERIVED = "INTRADAY_DERIVED"
EOD_DELAYED = "EOD_DELAYED"
SLOW_MACRO = "SLOW_MACRO"

def _iso(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)

def entry(name: str, clock: str, source: str, *, observed_at: Any = None,
          as_of: Any = None, status: str = "UNKNOWN",
          freshness_seconds: float | None = None,
          provenance: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "name": name, "clock": clock, "source": source,
        "observed_at": _iso(observed_at), "as_of": _iso(as_of),
        "status": status,
        "freshness_seconds": freshness_seconds,
        "provenance": provenance or {},
    }

def build_data_clock(parsed: dict[str, Any]) -> dict[str, Any]:
    raw = parsed.get("raw_series") or {}
    observed = parsed.get("observed_at") or parsed.get("retrieved_at")
    technical = parsed.get("technical_context") or {}
    source_oi = raw.get("totals") or {}
    option_status = "OK" if any(source_oi.get(k) is not None for k in
        ("open_interest_total", "open_interest_view_total", "oi_change_total")) else "UNKNOWN"
    auction_status = "OK" if (technical.get("auction") or {}).get("status") == "OK" else "UNKNOWN"
    macro_status = "OK" if (raw.get("macro_state") or {}).get("status") == "OK" else "UNKNOWN"
    flow_status = "OK" if (raw.get("order_flow") or {}).get("status") == "OK" else "UNKNOWN"
    return {
        "version": "data-clock-v1",
        "entries": [
            entry("futures_price", REALTIME, "quikstrike_snapshot", observed_at=observed,
                  status="OK" if parsed.get("future_price") is not None else "UNKNOWN"),
            entry("cfd_spot", REALTIME, str(parsed.get("spot_source") or "twelve_data"),
                  observed_at=((parsed.get("price_conversion") or {}).get("source_timestamp") or observed),
                  status="OK" if parsed.get("cfd_price") is not None else "UNKNOWN"),
            entry("options_oi_gamma", EOD_DELAYED, "cme_quikstrike",
                  observed_at=observed, as_of=raw.get("oi_as_of"),
                  status=option_status,
                  provenance={"oi_is_not_tick_flow": True}),
            entry("order_flow", INTRADAY_DERIVED, str((raw.get("order_flow") or {}).get("source") or "not_provided"),
                  observed_at=(raw.get("order_flow") or {}).get("observed_at"),
                  as_of=(raw.get("order_flow") or {}).get("as_of"),
                  status=flow_status),
            entry("auction_profile", INTRADAY_DERIVED, "twelve_data_ohlcv_bar_proxy",
                  observed_at=(technical.get("auction") or {}).get("observed_at"),
                  status=auction_status,
                  provenance={"mode": (technical.get("auction") or {}).get("mode", "BAR_PROXY")}),
            entry("macro", SLOW_MACRO, str((raw.get("macro_state") or {}).get("source") or "fred"),
                  observed_at=(raw.get("macro_state") or {}).get("observed_at"),
                  as_of=(raw.get("macro_state") or {}).get("as_of"),
                  status=macro_status),
            entry("cot", SLOW_MACRO, "cftc_cot",
                  observed_at=(raw.get("cot_state") or {}).get("observed_at"),
                  as_of=(raw.get("cot_state") or {}).get("as_of"),
                  status="OK" if raw.get("cot_state") else "UNKNOWN"),
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

def apply_data_clock(parsed: dict[str, Any]) -> dict[str, Any]:
    raw = parsed.setdefault("raw_series", {})
    state = raw.setdefault("market_state", {})
    clock = build_data_clock(parsed)
    raw["data_clock"] = clock
    state["data_clock"] = clock
    return parsed
