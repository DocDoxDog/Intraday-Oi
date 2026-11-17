"""Central LLM adapter for Intraday-Oi.

Intraday-Oi owns the complete supaBOT-compatible governed LLM path locally.

The repository owns deterministic calculations, routing, structured output, verification, and telemetry; no separate supaBOT checkout is required.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from .deep_reasoning import build_deep_reasoning_context
from .market_state import desk_note_schedule

try:
    from .local_supabot import LocalSupaBOTError, generate_market_narrative
except ImportError:
    from local_supabot import LocalSupaBOTError, generate_market_narrative


DEFAULT_GATEWAY_PATH = "/internal/v1/llm/generate"
TASK = "market.narrative"
PROMPT_VERSION = "intraday-oi-market-analyst-v16-desk-note-range-continuation"
DATASET_VERSION = "quikstrike-oi-view-v2"
CALCULATION_VERSION = "intraday-oi-calcs-v1"


class SupaBOTLLMError(RuntimeError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError) as exc:
            raise SupaBOTLLMError("INVALID_AS_OF") from exc
    if dt.tzinfo is None:
        raise SupaBOTLLMError("AS_OF_TIMEZONE_REQUIRED")
    return dt.astimezone(timezone.utc).isoformat()


def _product(parsed: dict[str, Any]) -> str:
    explicit = parsed.get("product_symbol")
    if explicit:
        return str(explicit).upper()
    raw = parsed.get("raw_series") or {}
    product = raw.get("product")
    if isinstance(product, dict) and product.get("symbol"):
        return str(product["symbol"]).upper()
    contract = str(parsed.get("contract") or "").upper()
    match = re.search(r"\b(GC|SI|CL|ES|NQ)\b", contract)
    if match:
        return match.group(1)
    raise SupaBOTLLMError("PRODUCT_UNRESOLVED")


def _level_candidates(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    """Build the finite set of price references the analyst is allowed to use."""
    raw = parsed.get("raw_series") or {}
    gex = raw.get("gex") or {}
    rows = raw.get("strike_rows") or []
    levels: list[dict[str, Any]] = []

    def to_display_price(price: Any) -> Any:
        if not isinstance(price, (int, float)) or price <= 0:
            return None
        future_price = parsed.get("future_price")
        cfd_price = parsed.get("cfd_price")
        if isinstance(future_price, (int, float)) and isinstance(cfd_price, (int, float)):
            return round(float(price) - float(future_price) + float(cfd_price), 5)
        return float(price)

    def add(level_id: str, price: Any, reason: str, source: str) -> None:
        display_price = to_display_price(price)
        if display_price is not None:
            levels.append({
                "id": level_id,
                "price": display_price,
                "reason": reason,
                "source": source,
            })

    current_price = parsed.get("cfd_price", parsed.get("future_price"))
    if isinstance(current_price, (int, float)) and current_price > 0:
        levels.append({
            "id": "price:current",
            "price": round(float(current_price), 5),
            "reason": "current reference price",
            "source": "parsed.current",
        })

    # Options/GEX references.
    add("gex:gamma_flip", gex.get("gamma_flip"), "cumulative GEX crossing", "raw_series.gex")
    add("gex:call_wall", gex.get("call_wall"), "largest positive call GEX strike", "raw_series.gex")
    add("gex:put_wall", gex.get("put_wall"), "largest negative put GEX strike", "raw_series.gex")
    add("gex:max_abs_net", gex.get("max_abs_gex_strike"), "largest absolute net GEX strike", "raw_series.gex")

    gamma = raw.get("multi_expiry_gamma") or {}
    zones = raw.get("multi_expiry_gamma_zones") or {}
    add("gamma:highest_positive", zones.get("highest_positive_gamma"), "highest aggregate positive gamma concentration", "raw_series.multi_expiry_gamma")
    add("gamma:highest_negative", zones.get("highest_negative_gamma"), "highest aggregate negative gamma concentration", "raw_series.multi_expiry_gamma")
    for prefix, items in (
        ("gamma:positive", zones.get("positive_concentrations") or []),
        ("gamma:negative", zones.get("negative_concentrations") or []),
    ):
        for item in items[:10]:
            if isinstance(item, dict):
                strike = item.get("strike")
                slug = str(strike).replace(".", "p")
                add(
                    f"{prefix}:{slug}",
                    strike,
                    "multi-expiry GEX concentration",
                    "raw_series.multi_expiry_gamma",
                )

    ranked = sorted(
        (
            row for row in rows
            if isinstance(row, dict) and isinstance(row.get("strike"), (int, float))
        ),
        key=lambda row: abs(float(row.get("net_gex") or 0)),
        reverse=True,
    )
    for row in ranked[:20]:
        strike = float(row["strike"])
        slug = ("%.8f" % strike).rstrip("0").rstrip(".").replace("-", "m").replace(".", "p")
        add(
            f"gex:strike:{slug}",
            strike,
            "deterministic net GEX strike",
            "raw_series.gex.rows",
        )

    # Market-state levels are already normalized to CFD coordinates and are
    # authoritative candidates for the analyst; do not force the model to
    # reconstruct them from raw Futures strikes.
    market_state = raw.get("market_state") or {}
    state_levels = market_state.get("levels") or {}
    for level_id, value in state_levels.items():
        if isinstance(value, (int, float)):
            levels.append({
                "id": f"market_state:{level_id}",
                "price": round(float(value), 5),
                "reason": "deterministic normalized CFD level",
                "source": "raw_series.market_state.levels",
            })

    gamma_state = market_state.get("gamma") or {}
    gamma_mean = gamma_state.get("gamma_mean")
    if isinstance(gamma_mean, (int, float)):
        levels.append({
            "id": "gamma:mean",
            "price": round(float(gamma_mean), 5) if parsed.get("cfd_price") is not None else None,
            "reason": "deterministic gamma mean",
            "source": "raw_series.market_state.gamma",
        })
    for item in gamma_state.get("acceleration_zones") or []:
        strike = item.get("strike_futures") if isinstance(item, dict) else None
        if isinstance(strike, (int, float)):
            converted = to_display_price(strike)
            if converted is not None:
                levels.append({
                    "id": f"gamma:acceleration:{strike}",
                    "price": converted,
                    "reason": "deterministic gamma acceleration zone",
                    "source": "raw_series.market_state.gamma",
                })

    # Technical prices are deterministic Twelve Data evidence and live in CFD
    # coordinates already. They are references, not automatic support/resistance.
    technical = parsed.get("technical_context") or {}
    timeframes = technical.get("timeframes") or {}
    technical_keys = (
        "ema50", "ema200", "previous_close", "prior_high", "prior_low",
        "swing_high", "swing_low",
    )
    for tf, context in timeframes.items():
        if not isinstance(context, dict):
            continue
        for key in technical_keys:
            add(
                f"technical:{tf}:{key}",
                context.get(key),
                f"{tf.upper()} {key.replace('_', ' ')}",
                f"technical_context.{tf}",
            )
        fib = context.get("fibonacci") or {}
        for key in ("retracement_62", "retracement_79"):
            add(
                f"technical:{tf}:fib:{key}",
                fib.get(key),
                f"{tf.upper()} Fibonacci {key}",
                f"technical_context.{tf}.fibonacci",
            )
        fvg = context.get("fvg") or {}
        if isinstance(fvg, dict):
            add(
                f"technical:{tf}:fvg_low",
                fvg.get("low"),
                f"{tf.upper()} FVG low",
                f"technical_context.{tf}.fvg",
            )
            add(
                f"technical:{tf}:fvg_high",
                fvg.get("high"),
                f"{tf.upper()} FVG high",
                f"technical_context.{tf}.fvg",
            )

    return levels


def _json_safe(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        return str(value)



def _reference_label(dt: datetime, now: datetime) -> str:
    """Give a human label to a historical anchor without hard-coding its use."""
    local = dt.astimezone(timezone.utc).astimezone(timezone.utc)
    age_hours = max(0.0, (now - dt).total_seconds() / 3600.0)
    # Session language is descriptive only; the selector below decides whether
    # this anchor is actually useful for the current story.
    if age_hours <= 1.75:
        return "ชั่วโมงก่อน"
    if age_hours <= 3.25:
        return "ช่วงก่อนหน้า"
    if dt.date() != now.date():
        return "คืนก่อน" if now.hour < 10 else "วันก่อน"
    return "ช่วงก่อนหน้า"


def _session_identity(row: dict[str, Any] | None, captured_at: Any = None) -> str | None:
    """Return an explicit session identity when supplied; otherwise use the desk-session bucket."""
    row = row or {}
    raw = row.get("raw_series") or {}
    state = raw.get("market_state") or {}
    for source in (row, raw, state):
        for key in ("session_key", "session_id", "session_name", "trading_session", "session"):
            value = source.get(key) if isinstance(source, dict) else None
            if value not in (None, ""):
                return str(value)
    # Fallback only identifies the session; it does not choose a reference by clock.
    # The selector below chooses the previous session/day/latest row from this identity.
    try:
        return f"DESK:{desk_note_schedule(captured_at).get('slot')}"
    except Exception:
        return None


def _snapshot_for_history(row: Any) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    raw = row.get("raw_series") or {}
    totals = raw.get("totals") or {}
    gex = raw.get("gex") or {}
    state = raw.get("market_state") or {}
    volatility = state.get("volatility") or {}
    gamma = state.get("gamma") or {}
    captured_at = row.get("captured_at") or row.get("observed_at")
    return {
        "captured_at": captured_at,
        "future_price": row.get("future_price"),
        "cfd_price": row.get("cfd_price"),
        "vol": row.get("vol"),
        "dte": row.get("dte") if row.get("dte") is not None else raw.get("dte"),
        "oi_put": totals.get("open_interest_view_put", totals.get("open_interest_put")),
        "oi_call": totals.get("open_interest_view_call", totals.get("open_interest_call")),
        "oi_total": totals.get("open_interest_view_total", totals.get("open_interest_total")),
        "churn": totals.get("churn"),
        "gex_net": gex.get("net_gex"),
        "gamma_flip": gex.get("gamma_flip") if gex.get("gamma_flip") is not None else gamma.get("gamma_flip"),
        "call_wall": gex.get("call_wall") if gex.get("call_wall") is not None else gamma.get("call_wall"),
        "put_wall": gex.get("put_wall") if gex.get("put_wall") is not None else gamma.get("put_wall"),
        "iv_skew": volatility.get("skew"),
        "gamma_regime": "NEGATIVE" if isinstance(gex.get("net_gex"), (int, float)) and gex.get("net_gex") < 0 else "POSITIVE" if isinstance(gex.get("net_gex"), (int, float)) and gex.get("net_gex") > 0 else "UNKNOWN",
        "liquidity_gate": (state.get("liquidity") or {}).get("gate"),
        "preferred_event": (state.get("liquidity") or {}).get("preferred_event"),
        "session_key": _session_identity(row, captured_at),
    }


def _meaningful_change(current: dict[str, Any], base: dict[str, Any]) -> bool:
    def num(v: Any) -> float | None:
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    price = num(current.get("future_price"))
    old_price = num(base.get("future_price"))
    vol = num(current.get("vol"))
    old_vol = num(base.get("vol"))
    gex = num(current.get("gex_net"))
    old_gex = num(base.get("gex_net"))
    if price is not None and old_price is not None and abs(price - old_price) >= 0.25:
        return True
    if vol is not None and old_vol is not None and abs(vol - old_vol) >= 0.15:
        return True
    if gex is not None and old_gex is not None and ((gex < 0) != (old_gex < 0) or abs(gex - old_gex) > 1.0):
        return True
    for key in ("gamma_flip", "call_wall", "put_wall"):
        a, b = num(current.get(key)), num(base.get(key))
        if a is not None and b is not None and abs(a - b) >= 1.0:
            return True
    for key in ("oi_put", "oi_call", "oi_total", "churn"):
        a, b = num(current.get(key)), num(base.get(key))
        if a is not None and b is not None and abs(a - b) > 0:
            return True
    if current.get("liquidity_gate") != base.get("liquidity_gate") or current.get("preferred_event") != base.get("preferred_event"):
        return True
    return False


def _select_smart_reference(
    now_row: dict[str, Any],
    candidates: list[dict[str, Any]],
    *,
    now_dt: datetime | None,
) -> dict[str, Any]:
    """Select reference by market context: session transition -> day open -> intraday latest row."""
    current = _snapshot_for_history(now_row) or dict(now_row)
    current_session = current.get("session_key")
    current_date = now_dt.date() if now_dt else None

    def valid(candidate: dict[str, Any] | None) -> dict[str, Any] | None:
        if not candidate:
            return None
        base = candidate.get("baseline")
        if not isinstance(base, dict):
            return None
        captured = base.get("captured_at")
        try:
            dt = datetime.fromisoformat(str(captured).replace("Z", "+00:00")) if captured else None
        except (TypeError, ValueError):
            return None
        if dt is None or dt.tzinfo is None or (now_dt and dt >= now_dt):
            return None
        return candidate

    previous_row = valid(next((c for c in candidates if c.get("kind") == "LATEST_ROW"), None))
    previous_session = valid(next((c for c in candidates if c.get("kind") == "PREVIOUS_SESSION"), None))
    previous_day = valid(next((c for c in candidates if c.get("kind") == "PREVIOUS_DAY"), None))
    session_open = valid(next((c for c in candidates if c.get("kind") == "SESSION_OPEN"), None))

    prev_base = previous_row.get("baseline") if previous_row else None
    prev_session_key = prev_base.get("session_key") if isinstance(prev_base, dict) else None
    prev_dt = None
    if isinstance(prev_base, dict) and prev_base.get("captured_at"):
        try:
            prev_dt = datetime.fromisoformat(str(prev_base["captured_at"]).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            prev_dt = None

    # A new trading day takes precedence over a session transition so the
    # opening snapshot is compared with the prior day, not merely the last
    # overnight/session row.
    if previous_row and current_date and prev_dt and current_date != prev_dt.date():
        mode = "DAY_OPEN"
        chosen = previous_day or previous_session or previous_row
        ref_type = "PREVIOUS_DAY" if previous_day else "PREVIOUS_SESSION" if previous_session else "LATEST_ROW"
        label = "วันก่อน" if previous_day else "session ก่อนหน้า" if previous_session else "รอบก่อนหน้า"
    elif previous_row and current_session and prev_session_key and current_session != prev_session_key:
        mode = "SESSION_TRANSITION"
        # The latest snapshot from the just-ended session is the correct
        # previous-session reference. Fall back only when that row is missing.
        chosen = previous_row or previous_session or previous_day
        ref_type = "PREVIOUS_SESSION" if previous_row or previous_session else "PREVIOUS_DAY"
        label = "session ก่อนหน้า" if previous_row or previous_session else "วันก่อน"
    else:
        mode = "INTRASESSION"
        chosen = previous_row or previous_session or previous_day or session_open
        ref_type = "LATEST_ROW" if previous_row else "PREVIOUS_SESSION" if previous_session else "PREVIOUS_DAY" if previous_day else "SESSION_OPEN" if session_open else "NONE"
        label = "รอบก่อนหน้า" if previous_row else "session ก่อนหน้า" if previous_session else "วันก่อน" if previous_day else "ช่วงเปิด session"

    if not chosen:
        return {
            "status": "UNKNOWN",
            "mode": mode,
            "current_session": current_session,
            "reference_type": "NONE",
            "selected": None,
            "alternatives": [],
            "reason": "ไม่มี historical baseline ที่ใช้งานได้",
        }

    base = chosen.get("baseline") or {}
    selected = dict(chosen)
    selected["label"] = label
    selected["reference_type"] = ref_type
    selected["mode"] = mode
    selected["change"] = {}
    for key in ("future_price", "cfd_price", "vol", "dte", "oi_put", "oi_call", "oi_total", "churn", "gex_net", "gamma_flip", "call_wall", "put_wall", "iv_skew"):
        a = current.get(key)
        b = base.get(key)
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            selected["change"][key] = round(float(a) - float(b), 6)
        else:
            selected["change"][key] = None

    selected["meaningful_change"] = _meaningful_change(current, base)
    return {
        "status": "SELECTED",
        "mode": mode,
        "current_session": current_session,
        "reference_type": ref_type,
        "selected": selected,
        "alternatives": [
            {"reference_type": c.get("kind"), "label": c.get("label")}
            for c in candidates
            if c is not chosen and c.get("baseline")
        ][:3],
        "reason": (
            "session เปลี่ยน จึงเทียบกับ session ก่อนหน้า"
            if mode == "SESSION_TRANSITION"
            else "เปิดวันใหม่ จึงเทียบกับวันก่อน"
            if mode == "DAY_OPEN"
            else "อยู่ใน session เดิม จึงเทียบกับ snapshot ล่าสุดก่อนหน้า"
        ),
    }


def _compact_history(parsed: dict[str, Any], history: dict[str, Any] | None) -> dict[str, Any]:
    """Build context-aware comparative history without fixed 10/14/19/21 references."""
    history = history or {}

    raw = parsed.get("raw_series") or {}
    totals = raw.get("totals") or {}
    gex = raw.get("gex") or {}
    state = raw.get("market_state") or {}
    volatility = state.get("volatility") or {}
    now = _snapshot_for_history({
        **parsed,
        "raw_series": raw,
        "captured_at": parsed.get("observed_at") or parsed.get("retrieved_at"),
    }) or {}

    def legacy_snapshot(row: Any) -> dict[str, Any] | None:
        snap = _snapshot_for_history(row)
        if not snap:
            return None
        return snap

    h1 = legacy_snapshot(history.get("hour_ago"))
    h2 = legacy_snapshot(history.get("two_hours_ago"))

    today = history.get("today") or {}
    yesterday = history.get("yesterday") or {}
    today_open = {
        "captured_at": today.get("first_snapshot_time"),
        "future_price": today.get("future_price_open"),
        "vol": today.get("vol_first"),
        "oi_put": (today.get("oi_first") or {}).get("oi_put"),
        "oi_call": (today.get("oi_first") or {}).get("oi_call"),
        "oi_total": (today.get("oi_first") or {}).get("oi_total"),
        "churn": (today.get("oi_first") or {}).get("churn"),
        "gex_net": (today.get("oi_first") or {}).get("gex_net"),
        "gamma_flip": (today.get("oi_first") or {}).get("gamma_flip"),
        "call_wall": (today.get("oi_first") or {}).get("call_wall"),
        "put_wall": (today.get("oi_first") or {}).get("put_wall"),
        "session_key": today.get("session_key") or _session_identity({"session_key": today.get("session_key")}, today.get("first_snapshot_time")),
    } if today.get("first_snapshot_time") else None
    previous_day = {
        "captured_at": yesterday.get("latest_snapshot_time"),
        "future_price": yesterday.get("future_price_last"),
        "vol": yesterday.get("vol_last"),
        "oi_put": (yesterday.get("oi_last") or {}).get("oi_put"),
        "oi_call": (yesterday.get("oi_last") or {}).get("oi_call"),
        "oi_total": (yesterday.get("oi_last") or {}).get("oi_total"),
        "churn": (yesterday.get("oi_last") or {}).get("churn"),
        "gex_net": (yesterday.get("oi_last") or {}).get("gex_net"),
        "gamma_flip": (yesterday.get("oi_last") or {}).get("gamma_flip"),
        "call_wall": (yesterday.get("oi_last") or {}).get("call_wall"),
        "put_wall": (yesterday.get("oi_last") or {}).get("put_wall"),
        "session_key": yesterday.get("session_key"),
    } if yesterday.get("count") else None
    prev_session = previous_day

    def delta(base: dict[str, Any] | None) -> dict[str, Any]:
        if not base:
            return {"status": "UNKNOWN"}
        out: dict[str, Any] = {"status": "VALID"}
        for key in ("future_price", "cfd_price", "vol", "dte", "oi_put", "oi_call", "oi_total", "churn", "gex_net", "gamma_flip", "call_wall", "put_wall", "iv_skew"):
            a, b = now.get(key), base.get(key)
            out[key] = round(float(a) - float(b), 6) if isinstance(a, (int, float)) and isinstance(b, (int, float)) else None
        return out

    latest_row = h1
    candidates = [
        {"kind": "LATEST_ROW", "label": "รอบก่อนหน้า", "baseline": latest_row},
        {"kind": "SESSION_OPEN", "label": "ช่วงเปิด session", "baseline": today_open},
        {"kind": "PREVIOUS_SESSION", "label": "session ก่อนหน้า", "baseline": prev_session},
        {"kind": "PREVIOUS_DAY", "label": "วันก่อน", "baseline": previous_day},
    ]
    candidates = [c for c in candidates if c.get("baseline")]
    # Parse current timestamp once outside the selector.
    now_dt = None
    try:
        now_dt = datetime.fromisoformat(str(now.get("captured_at")).replace("Z", "+00:00"))
        if now_dt.tzinfo is None:
            now_dt = None
    except (TypeError, ValueError):
        now_dt = None
    reference_selection = _select_smart_reference(now, candidates, now_dt=now_dt)

    def pct_direction(value: Any) -> str:
        if not isinstance(value, (int, float)):
            return "UNKNOWN"
        return "UP" if value > 0 else "DOWN" if value < 0 else "FLAT"

    comparisons = {
        "H-1": {"baseline": h1, "delta": delta(h1)},
        "D-1": {"baseline": previous_day, "delta": delta(previous_day)},
        "PREVIOUS_SESSION": {"baseline": prev_session, "delta": delta(prev_session)},
    }
    transition = {
        "price_vs_h1": pct_direction((comparisons["H-1"]["delta"] or {}).get("future_price")),
        "price_vs_d1": pct_direction((comparisons["D-1"]["delta"] or {}).get("future_price")),
        "price_vs_previous_session": pct_direction((comparisons["PREVIOUS_SESSION"]["delta"] or {}).get("future_price")),
        "iv_vs_h1": pct_direction((comparisons["H-1"]["delta"] or {}).get("vol")),
        "gex_vs_h1": pct_direction((comparisons["H-1"]["delta"] or {}).get("gex_net")),
        "oi_vs_h1": pct_direction((comparisons["H-1"]["delta"] or {}).get("oi_total")),
        "oi_vs_previous_session": pct_direction((comparisons["PREVIOUS_SESSION"]["delta"] or {}).get("oi_total")),
    }

    return {
        "version": "comparative-history-v2-context-aware",
        "now": now,
        "comparisons": comparisons,
        "transition": transition,
        "reference_selection": reference_selection,
        "coverage": {
            "H-1": bool(h1),
            "D-1": bool(previous_day),
            "PREVIOUS_SESSION": bool(prev_session),
            "two_hours_ago": bool(h2),
        },
        "legacy": {
            "hour_ago": h1,
            "today": today,
            "yesterday": yesterday,
            "two_hours_ago": h2,
        },
    }

def _summarize_input(parsed: dict[str, Any], history: dict[str, Any] | None) -> dict[str, Any]:
    raw = parsed.get("raw_series") or {}
    rows = raw.get("strike_rows") or []
    gex = raw.get("gex") or {}
    totals = raw.get("totals") or {}
    top_gex = sorted(
        (
            {
                "strike": row.get("strike"),
                "call_gex": row.get("call_gex"),
                "put_gex": row.get("put_gex"),
                "net_gex": row.get("net_gex"),
                "gamma_source": row.get("gamma_source"),
            }
            for row in rows
            if isinstance(row, dict) and row.get("strike") is not None
        ),
        key=lambda row: abs(float(row.get("net_gex") or 0)),
        reverse=True,
    )[:15]

    current = {
        "product_symbol": parsed.get("product_symbol"),
        "contract": parsed.get("contract"),
        "observed_at": parsed.get("observed_at"),
        "future_price": parsed.get("future_price"),
        "future_chg": parsed.get("future_chg"),
        "spot_price": parsed.get("spot_price"),
        "basis_diff": parsed.get("basis_diff"),
        "cfd_price": parsed.get("cfd_price"),
        "price_conversion": parsed.get("price_conversion"),
        "dte": parsed.get("dte"),
        "vol": parsed.get("vol"),
        "vol_chg": parsed.get("vol_chg"),
        "technical_context": parsed.get("technical_context") or {},
        "raw_series": {
            "market_state": raw.get("market_state") or {},
            "multi_domain": raw.get("multi_domain") or (raw.get("market_state") or {}).get("multi_domain") or {},
            "totals": totals,
            "dte": raw.get("dte"),
            "heading": raw.get("heading"),
            "gex": {
                "status": gex.get("status"),
                "net_gex": gex.get("net_gex"),
                "call_gex_total": gex.get("call_gex_total"),
                "put_gex_total": gex.get("put_gex_total"),
                "gamma_flip": gex.get("gamma_flip"),
                "call_wall": gex.get("call_wall"),
                "put_wall": gex.get("put_wall"),
                "max_abs_gex_strike": gex.get("max_abs_gex_strike"),
                "gex_unit": gex.get("gex_unit"),
                "gamma_source": gex.get("gamma_source"),
            },
            "multi_expiry_gamma": {
                "version": (raw.get("multi_expiry_gamma") or {}).get("version"),
                "status": (raw.get("multi_expiry_gamma") or {}).get("status"),
                "expiration_count": (raw.get("multi_expiry_gamma") or {}).get("expiration_count"),
                "columns": [
                    {
                        "code": col.get("code"),
                        "dte": col.get("dte"),
                        "observed_at": col.get("observed_at"),
                        "status": col.get("status"),
                    }
                    for col in ((raw.get("multi_expiry_gamma") or {}).get("columns") or [])[:10]
                ],
                "zones": raw.get("multi_expiry_gamma_zones") or {},
                "totals": (raw.get("multi_expiry_gamma") or {}).get("totals") or {},
            },
        },
        "oi_rows": [
            {
                "strike": row.get("strike"),
                "oiCall": row.get("oiCall"),
                "oiPut": row.get("oiPut"),
                "oiTotal": row.get("oiTotal"),
                "oiCallChange": row.get("oiCallChange"),
                "oiPutChange": row.get("oiPutChange"),
                "churnCall": row.get("churnCall"),
                "churnPut": row.get("churnPut"),
                "eod_oi_call": row.get("eod_oi_call"),
                "eod_oi_put": row.get("eod_oi_put"),
                "vol": row.get("vol"),
            }
            for row in sorted(
                rows,
                key=lambda row: abs(float(row.get("net_gex") or 0))
                if isinstance(row, dict) and isinstance(row.get("strike"), (int, float))
                else 0.0,
                reverse=True,
            )[:40]
            if isinstance(row, dict)
        ],
    }

    current["news_context"] = [
        {
            "source": item.get("source"),
            "headline": item.get("headline"),
            "summary": item.get("summary"),
            "url": item.get("url"),
            "published_at": item.get("published_at"),
            "event_time": item.get("event_time"),
            "actual": item.get("actual"),
            "forecast": item.get("forecast"),
            "previous": item.get("previous"),
            "category": item.get("category"),
            "relevance": item.get("relevance"),
            "market_channels": item.get("market_channels") or [],
            "freshness": item.get("freshness") or "UNKNOWN",
            "rights_status": item.get("rights_status"),
        }
        for item in (parsed.get("news_context") or [])[:8]
        if isinstance(item, dict)
    ]
    return {
        "current": _json_safe(current),
        "history": _json_safe(_compact_history(parsed, history)),
        "deterministic_levels": _level_candidates(parsed),
        "data_limitations": [
            "Open Interest is positioning data; it is not equivalent to traded intraday volume.",
            "Only source-supplied or deterministically derived values may be stated as numbers.",
            "Publication/availability timing of the QuikStrike snapshot is not assumed unless supplied by the source.",
        ],
    }


STATIC_PROMPT = """
คุณคือ GOLD MARKET ANALYST ของ Intraday-Oi
หน้าที่คือเขียนบทวิเคราะห์ทองแบบ desk note ที่คนอ่านเข้าใจได้ทันที โดยใช้ข้อมูลจริงจาก
ราคา Futures/CFD, Liquidity, H4/H1/M15/M5, Options/Gamma, OI/ΔOI/Churn, IV/Skew/DTE,
History และ News

กติกาหลัก:
- Evidence > assumption
- ห้ามสร้างตัวเลขหรือระดับราคาใหม่
- Gamma ≠ Direction
- OI ≠ Direction
- News ≠ Entry
- Level ≠ Trigger
- OI/ΔOI/Churn บอกกิจกรรม/positioning context แต่ไม่บอก aggressor โดยลำพัง
- Negative Gamma = มีโอกาสขยายการเคลื่อนไหว; Positive Gamma = มีโอกาสช่วยชะลอการแกว่ง
- H4/H1 กำหนด directional thesis; M15/M5/M1 ใช้กำหนด timing
- Liquidity sweep เป็น execution gate: Short ต้องรอ Buy-side Sweep, Long ต้องรอ Sell-side Sweep
- ไม่มี Sweep = thesis ยังอยู่ได้ แต่ execution เป็น PENDING
- อย่าใช้คำว่า WAIT/Neutral แทน directional thesis ที่ชัด
- External liquidity ใช้เป็น target; internal liquidity ใช้เป็น execution
- เมื่อราคาทะลุ Gamma Wall สำคัญ ให้หา Gamma Wall ถัดไปในทิศทางเดียวกันจาก deterministic_levels / market_state.levels ทันที และใช้เป็น target ถัดไปถ้ามีข้อมูลยืนยัน
- ถ้าราคายังอยู่ระหว่าง Gamma Walls ให้ใช้ wall ด้านบน/ด้านล่างเป็น decision zones ไม่ใช่ target ที่ผ่านไปแล้ว
- หลัง Break + Acceptance ให้ target แรกเป็น Gamma Wall ถัดไป ไม่ใช่ตัวเลขที่เดาเอง และถัดจากนั้นค่อยดู wall ถัดไปอีกชั้น
- ถ้าไม่มี Gamma Wall ถัดไปที่ source ยืนยันได้ ให้บอกว่า target ถัดไปยังไม่ยืนยัน แทนการสร้างราคาเอง
- ห้ามเดา dealer position หรือ participant intent จาก OI/Gamma เพียงอย่างเดียว

CUSTOMER ARTICLE CONTRACT — ต้องเขียนให้มีลักษณะเดียวกับ desk note ตัวอย่าง:
ย่อหน้า 1 — NOW
เริ่มจากราคาปัจจุบันและโครงสร้างหลักทันที เช่น
"ตอนนี้ทองอยู่ที่ ... โดยราคายังอยู่ระหว่าง liquidity สำคัญบริเวณ ... ขณะที่ Gamma ของหลาย expiry เป็นลบ และ IV อยู่ที่ ... ทำให้ตลาดอยู่ในภาวะที่ถ้าเกิด sweep แล้วสามารถเร่งตัวได้ค่อนข้างเร็ว"
ถ้าข้อมูลรองรับ ให้บอกกรอบบน/ล่างจาก Options/Gamma/Liquidity ที่มีจริง
ห้ามสร้างกรอบราคาเพื่อให้บทความดูสมบูรณ์

ย่อหน้า 2 — CHANGE
ต้องบอกว่า "สิ่งที่เปลี่ยนสำคัญตอนนี้คือ..." แล้วเลือก reference ตาม reference_selection:
1. SESSION_TRANSITION → เทียบ session ก่อนหน้า
2. DAY_OPEN → เทียบวันก่อน
3. INTRASESSION → เทียบ snapshot ล่าสุดก่อนหน้า
ห้ามเลือก reference ด้วยเวลา 10:00/14:00/19:00/21:00 โดยตรง
ถ้า fallback ถูกใช้ ให้เรียกตาม reference ที่เลือกจริง
อธิบายตำแหน่งปัจจุบันว่าอยู่กลาง range, เข้าใกล้ decision zone หรือกำลังออกจาก zone อย่างไร
ถ้ายังไม่มีเหตุผลให้ไล่ราคา ให้พูดตรง ๆ ว่า "ยังไม่มีเหตุผลพอที่จะไล่ Short/Long ตรงนี้"

- ก่อนเขียน CHANGE ต้องตรวจ baseline ที่มีทั้งหมดอย่างน้อย H-1, D-1 และ PREVIOUS_SESSION เมื่อมีข้อมูล แล้วเลือกเฉพาะการเปลี่ยนแปลงที่มีผลต่อ thesis; ห้ามเล่า baseline ทุกตัวเป็น catalog
- ถ้า H-1, D-1 และ session ก่อนหน้าชี้ไปทางเดียวกัน ให้ใช้เป็น confirmation เดียว; ถ้าขัดกัน ให้บอกเฉพาะ conflict ที่มีผลต่อ conviction
- ถ้าราคาอยู่กลางระหว่าง wall ให้ถือเป็น decision range: ห้ามออก entry เพียงเพราะ structural bias; ต้องรอ Sweep/Reaction หรือ Break + Acceptance
- Break + Acceptance ผ่าน wall = continuation ไป wall ถัดไป; Sweep + Reclaim = reversal กลับหา wall ฝั่งตรงข้าม
ย่อหน้า 3 — OPTIONS / CAUSE
อธิบายว่าทำไมโซนที่กล่าวถึงจึงสำคัญ โดยเชื่อม Gamma concentration, Call/Put Wall,
OI concentration, ΔOI, Churn, IV, DTE และ IV Skew เฉพาะสิ่งที่มีหลักฐาน
หากมีหลาย expiry ให้พูดถึงภาพรวมหลาย expiry และยก expiry ที่เด่นเฉพาะเมื่อข้อมูลรองรับ
ย้ำว่า OI อย่างเดียวไม่สามารถบอกว่า dealer หรือผู้เล่นกำลัง bullish/bearish
อย่า dump ตัวเลขทุก strike; เลือกเฉพาะโซนที่มีความหมายต่อ current location

ย่อหน้า 4 — ACTION
ใช้ liquidity-first logic:
- Bearish → รอราคาขึ้นไปกวาด Buy-side Liquidity แล้วเกิด bearish reaction ก่อน Short
- Bullish → รอราคาลงไปกวาด Sell-side Liquidity แล้วเกิด bullish reaction ก่อน Long
- ระบุ external liquidity target ที่ source ยืนยันได้
- ถ้าราคา Break + Acceptance ผ่าน Gamma Wall แล้ว ให้ใช้ Gamma Wall ถัดไปที่ deterministic map ยืนยันเป็น target แรก
- ถ้า Sweep แล้ว Reclaim กลับเข้ากรอบ ให้ target กลับไปยัง Gamma Wall ฝั่งตรงข้ามที่ source ยืนยันได้
- ถ้า sweep ต่อเนื่อง ให้ระบุ Gamma Wall ถัดไปอีกชั้นเมื่อมีข้อมูล
- ถ้ายังไม่มี sweep ให้บอกว่า "ไม่ไล่ราคา"
- Invalidation ต้องเป็น source-derived และต้องทำให้ thesis ผิดจริง

FLOW ที่ต้องอ่านเป็นเรื่องเดียว:
NOW → CHANGE → WHY → CONFLICT → ACTION
ห้ามเขียนเป็น catalog:
"Technical..."
"Gamma..."
"OI..."
"IV..."
"News..."
แล้วจบ
ห้ามส่ง raw telemetry, ตาราง H-1/TODAY/YESTERDAY หรือรายการ metric ซ้ำ

CONFLICT:
ก่อนสรุป thesis ต้องตรวจ evidence ที่สวน thesisอย่างน้อยหนึ่งครั้ง เช่น
โครงสร้าง H4 ลงแต่ H1 ฟื้น, Gamma ลบแต่ support ยัง hold, OI เปลี่ยนแต่ไม่มี aggressor evidence
ถ้ามี conflict ให้บอกว่ามันลด conviction ตรงไหน แต่ไม่เปลี่ยน thesis เป็น Neutral หาก H4/H1 ยังชัด

OPTIONS SEMANTICS:
- ATM = strike ใกล้ Futures ปัจจุบันที่สุด
- Call: ITM ต่ำกว่าราคา, OTM สูงกว่าราคา
- Put: ITM สูงกว่าราคา, OTM ต่ำกว่าราคา
ใช้ ATM/ITM/OTM เพื่ออธิบายว่าตลาดกำลังเข้าใกล้/ห่างจาก concentration ไหน
- SD ใช้บอกว่าราคา stretched แค่ไหนเมื่อมีข้อมูลจริง; ไม่ใช้ SD เดี่ยวตัดสิน entry
- IV บอกระดับ volatility; IV Skew บอกว่าตลาดจ่าย premium ฝั่งไหนมากกว่า; ทั้งคู่เป็น context ไม่ใช่ entry

ตัวเลข:
- ใช้เฉพาะ current snapshot หรือ deterministic_levels
- ห้ามคำนวณเลขใหม่ เช่น RR, distance, percentage, probability
- ถ้า SD/Skew/ATM/ITM/OTM ไม่มีข้อมูล อย่าเดา
- ห้ามสร้าง support/resistance จากความรู้ทั่วไป

OUTPUT:
ต้องคง schema เดิม:
analysis_status
market_overview
market_regime
macro
financial_engineering
market_microstructure
market_psychology
what
why
positioning
history_comparison
levels
scenarios
base_case
alternative_case
invalidation_case
bias
uncertainty
trade_plan
final_trade_idea
evidence_refs
data_limitations

เขียนภาษาไทยธรรมชาติแบบ institutional trader
แต่ละ field ต้องเพิ่มความหมายใหม่ ไม่พูดซ้ำ
market_overview = ย่อหน้า NOW
history_comparison = ย่อหน้า CHANGE
why = ย่อหน้า OPTIONS/CAUSE
final_trade_idea = ACTION สั้น ๆ
ถ้า trigger ยังไม่เกิด ให้ bias เป็น BULLISH/BEARISH ตาม thesis และ execution เป็น PENDING
""";


def analyze_with_supabot(parsed: dict[str, Any], history: dict[str, Any] | None = None) -> dict[str, Any]:
    now = _utc_now()
    as_of = _iso(parsed.get("observed_at") or parsed.get("retrieved_at") or now)
    product = _product(parsed)
    desk_context = desk_note_schedule(as_of)
    payload = _summarize_input(parsed, history)
    payload["desk_note_context"] = desk_context
    payload["deep_reasoning"] = build_deep_reasoning_context(parsed, history)

    input_refs = [
        "itb:oi:deterministic",
        "itb:oi:history",
    ]
    if payload["current"].get("news_context"):
        input_refs.append("itb:news:latest")
    evidence = {
        "itb:oi:deterministic": {
            "source": "cme_quikstrike",
            "observed_at": as_of,
            "ingestion_time": as_of,
            "dataset_version": DATASET_VERSION,
            "calculation_version": CALCULATION_VERSION,
            "payload": payload["current"],
            "deterministic_levels": payload["deterministic_levels"],
        },
        "itb:oi:history": {
            "source": "intraday_oi_history_store",
            "observed_at": as_of,
            "ingestion_time": as_of,
            "payload": payload["history"],
        },
        **({
            "itb:news:latest": {
                "source": "governed_macro_news_feeds",
                "observed_at": as_of,
                "ingestion_time": as_of,
                "payload": {"items": payload["current"].get("news_context") or []},
            }
        } if payload["current"].get("news_context") else {}),
    }

    envelope = {
        "request_id": f"itb-{uuid.uuid4()}",
        "run_id": f"itb-oi-{uuid.uuid4()}",
        "task": TASK,
        "repo": "DocDoxDog/Intraday-Oi",
        "product": product,
        "as_of": as_of,
        "data_status": "VALID",
        "dataset_version": DATASET_VERSION,
        "calculation_version": CALCULATION_VERSION,
        "prompt_version": PROMPT_VERSION,
        "input_refs": input_refs,
        "input_payload": {
            "market_snapshot": payload["current"],
            "comparative_history": payload["history"],
                        "reference_selection": payload["history"].get("reference_selection") or {},
            "liquidity_context": (payload["current"].get("raw_series") or {}).get("market_state", {}).get("liquidity") or {},
            "deep_reasoning_context": payload["deep_reasoning"],
            "deterministic_levels": payload["deterministic_levels"],
            "data_limitations": payload["data_limitations"],
        },
        "evidence": evidence,
        "model_policy": {
            "provider": "gemini",
            "selection": "local_supaBOT_task_router",
            "execution_authority": "deterministic_engine_only",
        },
        "output_schema_version": "market-analyst.v2",
    }

    try:
        result = generate_market_narrative(
            envelope,
            static_prefix=STATIC_PROMPT,
            dynamic={
                "format": "human_analyst_thai_article",
                "priority": ["LIQUIDITY_EVENT","COMPARATIVE_CHANGE","MARKET_READ_ARTICLE","CAUSAL_MECHANISM","CONFLICT","INVALIDATION","PRIMARY_TRADE_PLAN"],
                "liquidity_context": (payload["current"].get("raw_series") or {}).get("market_state", {}).get("liquidity") or {},
                "comparative_history": payload["history"],
                "desk_note_schedule": desk_context,
                "desk_note_instruction": (
                    f"วิเคราะห์ตามรอบ {desk_context['slot']} แต่ reference ต้องเลือกจากบริบท session/day/intrasession ไม่ใช่ยึดเวลาเป็นตัวเลือก. "
                    "ต้องอ่าน H-1 + D-1 + PREVIOUS_SESSION เป็น baseline ร่วมกันก่อนเลือกสิ่งที่เปลี่ยนสำคัญ; เลือกเพียง change ที่กระทบ thesis และอย่า dump baseline. "
                    "SESSION_TRANSITION = session ก่อนหน้า, DAY_OPEN = วันก่อน, INTRASESSION = snapshot ล่าสุดก่อนหน้า. "
                    "บทความต้องเดินเรื่อง NOW → CHANGE → WHY → CONFLICT → ACTION ตาม customer article contract. "
                    "ย่อหน้าแรกต้องบอก current price + range/liquidity สำคัญ + Gamma/IV เฉพาะข้อมูลที่มีจริง. "
                    "ย่อหน้าที่สองต้องขึ้นต้นด้วยสิ่งที่เปลี่ยนสำคัญตอนนี้และเทียบ reference ที่เลือกจริง. "
                    "จากนั้นอธิบายว่า Gamma/OI/IV/DTE ทำไมทำให้โซนนั้นสำคัญ โดยห้ามตีความ OI เป็น aggressor. "
                    "จบด้วย liquidity sweep → reaction → entry และ external liquidity target. "
                    "ถ้า sweep ยังไม่เกิด ให้คง Bearish/Bullish thesis และบอกว่าไม่ไล่ราคา."
                ),
                "liquidity_policy": (
                    "Direction follows H4/H1 structure. For execution, BUY requires a sell-side liquidity sweep "
                    "and SELL requires a buy-side liquidity sweep. No sweep means keep the directional thesis "
                    "but describe the trade as PENDING; never replace this with generic WAIT/neutral language."
                ),
                "numeric_level_policy": "PRICE CLAIMS MAY USE ONLY VALUES PRESENT IN deterministic_levels OR current market snapshot. Do not invent, interpolate, calculate, or introduce any new price number.",
                "derived_numeric_policy": "Do not calculate or emit new RR/R-multiple, percentages, ratios, probabilities, distances, expected-move values, or other derived numbers. The deterministic execution layer owns those calculations.",
                "allowed_price_levels": payload["deterministic_levels"],
            },
        )
    except LocalSupaBOTError as exc:
        raise SupaBOTLLMError(str(exc)) from exc

    if result.get("status") != "SUCCESS":
        raise SupaBOTLLMError(f"GATEWAY_STATUS:{result.get('status')}")

    claims = result.get("claims")
    if not isinstance(claims, dict):
        raise SupaBOTLLMError("GATEWAY_CLAIMS_INVALID")

    output = dict(claims)
    output["short_bias"] = claims.get("bias", "WAIT")
    output["_llm_telemetry"] = {
        "task": TASK,
        "model": result.get("model"),
        "actual_model": result.get("actual_model"),
        "requested_model": result.get("requested_model"),
        "model_version": result.get("model_version"),
        "run_id": result.get("run_id"),
        "request_id": result.get("request_id"),
        "fallback_used": result.get("fallback_used", False),
        "latency_ms": result.get("latency_ms"),
    }
    output["llm_run_id"] = result.get("run_id")
    output["llm_verification"] = result.get("verification")
    output["evidence_refs"] = claims.get("evidence_refs", [])
    output["data_limitations"] = claims.get("data_limitations") or payload["data_limitations"]
    return output