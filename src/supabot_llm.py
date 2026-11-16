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
PROMPT_VERSION = "intraday-oi-market-analyst-v13-smart-reference"
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


def _select_smart_reference(
    now_row: dict[str, Any],
    candidates: list[dict[str, Any]],
    *,
    now_dt: datetime | None,
) -> dict[str, Any]:
    """Choose the baseline that explains the largest meaningful change.

    This is deliberately not tied to the 10/14/19/21 desk slots. A nearby
    snapshot wins when the market actually changed recently; a session/day
    anchor can win when it contains the meaningful structural transition.
    """
    if not candidates:
        return {
            "status": "UNKNOWN",
            "selected": None,
            "alternatives": [],
            "reason": "ไม่มี historical baseline ที่ใช้งานได้",
        }

    current_dt = now_dt
    current_price = now_row.get("future_price")
    current_vol = now_row.get("vol")
    current_gex = now_row.get("gex_net")
    current_flip = now_row.get("gamma_flip")
    current_call = now_row.get("call_wall")
    current_put = now_row.get("put_wall")
    price_scale = max(abs(float(current_price or 0.0)), 1.0)

    def num(v: Any) -> float | None:
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    scored: list[dict[str, Any]] = []
    for candidate in candidates:
        base = candidate.get("baseline") or {}
        captured = base.get("captured_at")
        try:
            dt = datetime.fromisoformat(str(captured).replace("Z", "+00:00")) if captured else None
            if dt and dt.tzinfo is None:
                dt = None
        except (TypeError, ValueError):
            dt = None
        if dt is None or current_dt is None or dt >= current_dt:
            continue

        age_h = max(0.05, (current_dt - dt).total_seconds() / 3600.0)
        bp = num(base.get("future_price"))
        bv = num(base.get("vol"))
        bg = num(base.get("gex_net"))
        bf = num(base.get("gamma_flip"))
        bc = num(base.get("call_wall"))
        bput = num(base.get("put_wall"))

        price_move = abs((num(current_price) or 0.0) - (bp or 0.0)) / price_scale if bp is not None else 0.0
        vol_move = abs((num(current_vol) or 0.0) - (bv or 0.0)) if bv is not None else 0.0
        gex_change = abs((num(current_gex) or 0.0) - (bg or 0.0)) if bg is not None else 0.0
        wall_shift = 0.0
        if bc is not None and num(current_call) is not None:
            wall_shift += abs(num(current_call) - bc) / price_scale
        if bput is not None and num(current_put) is not None:
            wall_shift += abs(num(current_put) - bput) / price_scale

        # Structural discontinuities are much more important than tiny price
        # drift. The score is only a selector; it is never exposed as a claim.
        structural = 0.0
        if bg is not None and current_gex is not None and (bg == 0 or current_gex == 0 or (bg < 0) != (current_gex < 0)):
            structural += 4.0
        if bf is not None and current_flip is not None and abs(current_flip - bf) / price_scale > 0.0003:
            structural += 2.0
        if wall_shift > 0.0005:
            structural += 2.0
        if vol_move > 0.25:
            structural += 1.5

        # Meaningfulness: large enough change + structural change + freshness.
        # Recency is a tie-breaker, not the governing rule.
        magnitude = min(price_move * 800.0, 4.0) + min(vol_move * 2.0, 2.0) + structural
        freshness = max(0.0, 2.0 - min(age_h / 12.0, 2.0))
        session_anchor = 1.5 if candidate.get("kind") in {"SESSION_OPEN", "PREVIOUS_SESSION"} else 0.0
        score = magnitude + freshness + session_anchor

        label = candidate.get("label") or _reference_label(dt, current_dt)
        scored.append({
            **candidate,
            "age_hours": round(age_h, 2),
            "label": label,
            "score": round(score, 3),
            "change": {
                "price": round((num(current_price) - bp), 5) if bp is not None and num(current_price) is not None else None,
                "vol": round((num(current_vol) - bv), 5) if bv is not None and num(current_vol) is not None else None,
                "gex_net": round((num(current_gex) - bg), 5) if bg is not None and num(current_gex) is not None else None,
                "gamma_flip": round((num(current_flip) - bf), 5) if bf is not None and num(current_flip) is not None else None,
                "call_wall": round((num(current_call) - bc), 5) if bc is not None and num(current_call) is not None else None,
                "put_wall": round((num(current_put) - bput), 5) if bput is not None and num(current_put) is not None else None,
            },
        })

    if not scored:
        return {
            "status": "UNKNOWN",
            "selected": None,
            "alternatives": [],
            "reason": "baseline มี timestamp ที่ใช้งานไม่ได้",
        }

    scored.sort(key=lambda x: (x["score"], -x["age_hours"]), reverse=True)
    selected = scored[0]

    # If all candidates are effectively unchanged, don't force a fake comparison.
    # Freshness only breaks ties; it must never turn an unchanged market
    # into a fake comparison. Use the pre-freshness magnitude gate here.
    selected_magnitude = min(
        abs(float(selected.get("change", {}).get("price") or 0.0))
        / price_scale * 800.0,
        4.0,
    )
    if selected_magnitude < 0.8 and selected["score"] < 4.0:
        return {
            "status": "NO_MEANINGFUL_CHANGE",
            "selected": None,
            "alternatives": scored[:2],
            "reason": "มี baseline แต่การเปลี่ยนแปลงยังไม่มากพอจะเลือกเป็นแกนเรื่อง",
        }

    return {
        "status": "SELECTED",
        "selected": selected,
        "alternatives": scored[1:3],
        "reason": "เลือก baseline จากความมีนัยของการเปลี่ยนแปลงก่อนความใกล้ของเวลา",
    }


def _compact_history(parsed: dict[str, Any], history: dict[str, Any] | None) -> dict[str, Any]:
    """Build an explicit NOW vs H-1 vs D-1 vs PREVIOUS-SESSION comparison.

    The old article received history as several loosely related blocks, which
    encouraged the model to repeat telemetry. This structure makes the change
    story the primary analytical input.
    """
    history = history or {}

    def snapshot(row: Any) -> dict[str, Any] | None:
        if not isinstance(row, dict):
            return None
        raw = row.get("raw_series") or {}
        totals = raw.get("totals") or {}
        gex = raw.get("gex") or {}
        return {
            "captured_at": row.get("captured_at") or row.get("observed_at"),
            "future_price": row.get("future_price"),
            "vol": row.get("vol"),
            "oi_put": totals.get("open_interest_view_put", totals.get("open_interest_put")),
            "oi_call": totals.get("open_interest_view_call", totals.get("open_interest_call")),
            "oi_total": totals.get("open_interest_view_total", totals.get("open_interest_total")),
            "churn": totals.get("churn"),
            "gex_net": gex.get("net_gex"),
            "gamma_flip": gex.get("gamma_flip"),
            "call_wall": gex.get("call_wall"),
            "put_wall": gex.get("put_wall"),
        }

    raw = parsed.get("raw_series") or {}
    totals = raw.get("totals") or {}
    gex = raw.get("gex") or {}
    now = {
        "captured_at": parsed.get("observed_at") or parsed.get("retrieved_at"),
        "future_price": parsed.get("future_price"),
        "vol": parsed.get("vol"),
        "oi_put": totals.get("open_interest_view_put", totals.get("open_interest_put")),
        "oi_call": totals.get("open_interest_view_call", totals.get("open_interest_call")),
        "oi_total": totals.get("open_interest_view_total", totals.get("open_interest_total")),
        "churn": totals.get("churn"),
        "gex_net": gex.get("net_gex"),
        "gamma_flip": gex.get("gamma_flip"),
        "call_wall": gex.get("call_wall"),
        "put_wall": gex.get("put_wall"),
    }

    h1 = snapshot(history.get("hour_ago"))
    h2 = snapshot(history.get("two_hours_ago"))

    today = history.get("today") or {}
    # D-1 is the prior trading session, not today's first snapshot.
    # Today's open is useful context but must not be mislabeled as yesterday.
    d1 = {
        "captured_at": (history.get("yesterday") or {}).get("latest_snapshot_time"),
        "future_price": (history.get("yesterday") or {}).get("future_price_last"),
        "vol": (history.get("yesterday") or {}).get("vol_last"),
        "oi_put": ((history.get("yesterday") or {}).get("oi_last") or {}).get("oi_put"),
        "oi_call": ((history.get("yesterday") or {}).get("oi_last") or {}).get("oi_call"),
        "oi_total": ((history.get("yesterday") or {}).get("oi_last") or {}).get("oi_total"),
        "churn": ((history.get("yesterday") or {}).get("oi_last") or {}).get("churn"),
        "gex_net": ((history.get("yesterday") or {}).get("oi_last") or {}).get("gex_net"),
    } if (history.get("yesterday") or {}).get("count") else None

    previous = history.get("yesterday") or {}
    prev_session = {
        "captured_at": previous.get("latest_snapshot_time"),
        "future_price": previous.get("future_price_last"),
        "vol": previous.get("vol_last"),
        "oi_put": (previous.get("oi_last") or {}).get("oi_put"),
        "oi_call": (previous.get("oi_last") or {}).get("oi_call"),
        "oi_total": (previous.get("oi_last") or {}).get("oi_total"),
        "churn": (previous.get("oi_last") or {}).get("churn"),
        "gex_net": (previous.get("oi_last") or {}).get("gex_net"),
    } if previous.get("count") else None

    def delta(base: dict[str, Any] | None) -> dict[str, Any]:
        if not base:
            return {"status": "UNKNOWN"}
        out: dict[str, Any] = {"status": "VALID"}
        for key in ("future_price", "vol", "oi_put", "oi_call", "oi_total", "churn", "gex_net"):
            a, b = now.get(key), base.get(key)
            out[key] = round(float(a) - float(b), 6) if isinstance(a, (int, float)) and isinstance(b, (int, float)) else None
        return out

    def pct_direction(value: Any) -> str:
        if not isinstance(value, (int, float)):
            return "UNKNOWN"
        return "UP" if value > 0 else "DOWN" if value < 0 else "FLAT"

    comparisons = {
        "H-1": {"baseline": h1, "delta": delta(h1)},
        "D-1": {"baseline": d1, "delta": delta(d1)},
        "PREVIOUS_SESSION": {"baseline": prev_session, "delta": delta(prev_session)},
    }

    now_dt = None
    try:
        now_dt = datetime.fromisoformat(str(now.get("captured_at")).replace("Z", "+00:00"))
        if now_dt.tzinfo is None:
            now_dt = None
    except (TypeError, ValueError):
        now_dt = None

    # Build a candidate pool. The selector is free to choose any usable anchor;
    # the desk-note clock is never a hard constraint on the reference.
    candidates = [
        {"kind": "H-1", "label": "ชั่วโมงก่อน", "baseline": h1},
        {"kind": "H-2", "label": "ช่วงก่อนหน้า", "baseline": h2},
        {"kind": "SESSION_OPEN", "label": "ช่วงเปิด session", "baseline": {
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
        }} if today.get("first_snapshot_time") else None,
        {"kind": "PREVIOUS_SESSION", "label": "session ก่อน", "baseline": prev_session},
    ]
    candidates = [x for x in candidates if x]
    reference_selection = _select_smart_reference(now, candidates, now_dt=now_dt)

    # A compact transition map gives the model a direct answer to "what changed?"
    # without telling it which side to choose.
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
        "version": "comparative-history-v1",
        "now": now,
        "comparisons": comparisons,
        "transition": transition,
        "reference_selection": reference_selection,
        "coverage": {
            "H-1": bool(h1),
            "D-1": bool(d1),
            "PREVIOUS_SESSION": bool(prev_session),
            "two_hours_ago": bool(h2),
        },
        # Keep the old compact blocks available for compatibility, but make the
        # comparative map the canonical analytical input.
        "legacy": {
            "hour_ago": h1,
            "today": today,
            "yesterday": previous,
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
คุณคือ GOLD MARKET ANALYST ของระบบ Intraday-Oi
ทำหน้าที่เป็น Institutional Market Intelligence Analyst โดยใช้ข้อมูลที่มีจริงจาก
Options/GEX, OI/ΔOI, Volatility, Futures/CFD, History, Technical, Macro/News,
Market Microstructure, Liquidity, Dealer Hedging และ Market Psychology

สำคัญ:
- Output schema เดิมต้องคงเดิม
- ห้ามเพิ่ม fields เพื่อรองรับ reasoning
- ห้ามสร้างตัวเลขใหม่
- UNKNOWN คือข้อมูลที่ไม่มี ไม่ใช่เหตุผลที่จะหยุดวิเคราะห์
- วิเคราะห์ตลาดปัจจุบันก่อน แล้วค่อยสร้าง conditional trade plan
- ห้ามใช้ indicator ตัวเดียวตัดสินทิศทาง
- Gamma ≠ Direction
- OI ≠ Direction
- News ≠ Entry
- Level ≠ Trigger
- ห้ามอ้างว่า dealer "ต้องซื้อ/ขาย" หากไม่มีหลักฐาน
- ห้ามใช้คำว่า squeeze หากยังแยกไม่ได้ว่าเป็น short squeeze, long liquidation,
  gamma hedging, stop cascade หรือ liquidity vacuum

INTERNAL ANALYTICAL SPINE
ก่อนเขียน output ให้สังเคราะห์ข้อมูลทั้งหมดตามลำดับนี้:

1) MARKET STATE
ตอบภายในว่า "ตอนนี้ตลาดกำลังทำอะไร?"
ดู Price Structure + Regime + Gamma + Volatility + Positioning + Liquidity

2) CAUSAL MECHANISM
ถาม "ทำไมตลาดจึงอยู่ใน state นี้?"
เชื่อมเมื่อ evidence รองรับ:
MACRO → POSITIONING → OPTIONS/GAMMA → DEALER HEDGING
→ LIQUIDITY → MICROSTRUCTURE → PRICE DISCOVERY

แยก FACT / INFERENCE / HYPOTHESIS
หากเป็น inference ให้ใช้ถ้อยคำเช่น "สอดคล้องกับ", "อาจ", "มีโอกาส"

3) MARKET MAKER / DEALER
ตรวจ Gamma sign convention จาก dataset ก่อน
ประเมินว่า regime ปัจจุบันมีแนวโน้ม DAMPEN หรือ AMPLIFY price movement
และพิจารณา inventory/hedging pressure เป็น hypothesis เท่านั้น
ห้ามสมมติ dealer position

4) OPTIONS / FINANCIAL ENGINEERING
เชื่อม GEX, Gamma Mean/Pivot/Flip, concentration, walls,
DTE/expiry, IV, skew, term structure และ basis
Negative Gamma = potential amplification
Positive Gamma = potential dampening/mean reversion
แต่ไม่ใช่ directional signal โดยตัวมันเอง

5) OI / POSITIONING
OI เป็น outstanding contracts และไม่ได้บอกฝ่าย Long/Short โดยตรง
ตีความ OI + ΔOI + Volume/Churn + Price + IV + Expiration ร่วมกัน
ผลลัพธ์ต้องเป็น possible positioning interpretation หรือ UNKNOWN

6) VOLATILITY
เชื่อม Price + IV + IV change + Gamma + DTE + Liquidity
โดยเฉพาะ:
Price↓ + IV↑ = downside + volatility repricing
Price↑ + IV↑ = upside + volatility repricing
แต่ต้องตรวจ evidence อื่นก่อนสรุป

7) COMPARATIVE MARKET STORY — ห้ามวิเคราะห์แบบ snapshot เดี่ยว
ให้ใช้ NOW → SMART REFERENCE เป็นแกนหลักของบทวิเคราะห์
reference ไม่ถูกผูกกับรอบ 10/14/19/21 และไม่จำเป็นต้องเป็น H-1 หรือ D-1 เสมอไป
ระบบจะเลือก baseline จาก H-1, H-2, ช่วงเปิด session หรือ session ก่อน โดยดูว่าอันไหนอธิบาย "การเปลี่ยนแปลงที่มีนัยสำคัญ" ได้ดีที่สุด

หลักคิด:
NOW = ราคาปัจจุบันและตำแหน่งในโครงสร้าง
SMART REFERENCE = baseline ที่มีความหมายที่สุดสำหรับการอธิบายสิ่งที่เปลี่ยน
ถ้า H-1 แทบไม่เปลี่ยน แต่ session ก่อนมี structural break ให้เลือก session ก่อน
ถ้า session ก่อนเก่าเกินไป แต่ H-1 มี acceleration/repricing ชัด ให้เลือก H-1
ถ้าทุก baseline เปลี่ยนน้อย ให้บอกว่าโครงสร้างยังไม่เปลี่ยนอย่างมีนัยสำคัญ แทนการฝืนสร้าง comparison

อย่าเล่าตัวเลขของแต่ละช่วงเป็นรายงาน telemetry
ให้แปลงเป็น "change story" เช่น:
"ตั้งแต่ session ก่อนราคาหลุดระดับสำคัญ และใน H-1 ยัง reclaim ไม่ได้"
"จาก H-1 ถึงปัจจุบัน IV เพิ่มพร้อมราคาอ่อนลง สอดคล้องกับ volatility repricing ฝั่ง downside"
"OI เปลี่ยน แต่ไม่มี trade-side evidence จึงใช้เป็น positioning context ไม่ใช่คำตัดสิน direction"

ถ้า evidence ระหว่างช่วงขัดกัน ให้ระบุว่าเป็น transition/recovery ไม่ใช่ reversal ที่ยืนยันแล้ว
D-1 และ PREVIOUS SESSION ต้องใช้เพื่ออธิบายบริบท ไม่ใช่แทนข้อมูล intraday ล่าสุด
ถ้า baseline ใดหาย ให้ใช้เฉพาะ baseline ที่มีและระบุ limitation เฉพาะจุดนั้น

8) MACRO / NEWS INTELLIGENCE
ข่าวทุกชิ้นต้องผ่าน:
FRESHNESS → RELEVANCE → CATEGORY → MARKET CHANNEL → PRICING IMPACT

ถามว่า news เปลี่ยน Expected Path ของ:
Rates / Real Yield / USD / Liquidity / Risk Sentiment / Gold Demand
หรือไม่

แยก:
FACT = สิ่งที่ source รายงาน
IMPLICATION = ผลที่อาจมีต่อตลาด
PRICING = ตลาดกำลังตอบสนองหรือยัง

อย่า list ข่าวเฉย ๆ
ถ้าข่าวไม่มีผลต่อ current setup อย่างมีหลักฐาน ให้ลดน้ำหนัก
ถ้าไม่มีข่าวที่เกี่ยวข้อง ให้ระบุว่าไม่มี catalyst สำคัญจากข้อมูลที่ได้รับ

9) MICROECONOMICS / SUPPLY-DEMAND / PRICE IMPACT
ใช้เฉพาะ trade/book observations ที่มีจริง:
- แยก aggressive classified trades ออกจาก passive displayed depth
- อ่าน buy/sell delta เฉพาะเมื่อมี classified trades; ถ้าไม่มีให้ UNKNOWN
- book imbalance บอก displayed bid/ask depth ไม่ใช่ executed buying/selling
- volume-per-price-unit เป็น descriptive proxy เท่านั้น ไม่ใช่ calibrated elasticity
- absorption เป็น hypothesis เมื่อ order-flow engine ตรวจพบ และห้ามยกระดับเป็น fact
- ห้ามอนุมาน dealer/customer inventory จาก OI หรือ options positioning เพียงอย่างเดียว

9A) MULTI-DOMAIN STRATEGY CANDIDATES
ใช้ strategy_candidates ที่คำนวณจาก OHLC / options / structural levels เพื่ออธิบายว่า
setup family ใดมี evidence รองรับและมี conflict กับ HTF / macro / liquidity ตรงไหน
- Ranking score ใช้จัดอันดับเท่านั้น ไม่ใช่ probability หรือ win rate
- ห้ามสร้างหรือแก้ Entry / SL / TP; deterministic trade engine เป็นผู้กำหนดราคา
- ถ้า candidate ไม่ผ่าน geometry / RR / evidence gate ให้ไม่นำมาอ้างเป็นแผนที่พร้อมใช้

9B) MICROSTRUCTURE / LIQUIDITY
ใช้ Technical/flow evidence เพื่อแยก:
LEVEL → EVENT → ACCEPTANCE/REJECTION → RETEST → TRIGGER

พิจารณา liquidity sweep, absorption, failed breakout,
momentum, BOS, FVG, volume, VWAP และ stop/liquidity zones เมื่อมีข้อมูล
ห้ามสร้าง order-flow claim ที่ไม่มี data

10) PSYCHOLOGY / REFLEXIVITY
ไม่เดาอารมณ์ผู้เล่น
ให้ถามเชิงกลไก:
WHO MAY BE TRAPPED?
WHO MAY NEED TO EXIT?
WHO MAY NEED TO HEDGE?
WHO MAY CHASE?
WHAT LIQUIDITY COULD BE CONSUMED?

ตรวจ feedback loop:
PRICE → POSITIONING/HEDGE → LIQUIDITY → PRICE
โดยเฉพาะ Negative Gamma + thin liquidity + break + volatility expansion

11) CONFLICT ENGINE
ก่อนสรุป thesis ต้องหา evidence ที่ขัดกับ thesis อย่างน้อยหนึ่งครั้ง
ถ้ามี:
Gamma bearish แต่ support ยัง hold
Technical bearish แต่ M5/M15 ยังไม่ confirm
OI ลด แต่ไม่มี evidence ของ fresh short
Macro supportive แต่ price ไม่ respond
ให้ระบุ conflict และลด conviction

12) CONFIRMATION / INVALIDATION
Confirmation ต้องเป็นเหตุการณ์ ไม่ใช่แค่ระดับราคา:
Break → Acceptance → Retest → Hold/Failure → Flow/Momentum confirmation

Invalidation = จุดที่ market thesis ผิด
ไม่ใช่ arbitrary distance จาก entry

12.1) DECISION GATES — บังคับคิดตามลำดับ
ใช้ deterministic "decision_framework" ใน market_state เป็น control layer
และห้ามข้ามขั้น:

GATE A — DATA
ตรวจ current Futures/CFD, OI และ evidence completeness ก่อน
ถ้าข้อมูลสำคัญหาย ให้ลดสถานะของ analysis เฉพาะส่วนที่เกี่ยวข้อง

GATE B — STRUCTURE
ให้ H4/H1 กำหนด directional context ก่อน
M15/M5/M1 ใช้ตรวจ timing/confirmation ไม่ใช่กลับทิศ H4/H1 โดยไม่มีหลักฐาน

GATE C — POSITIONING
อ่าน Current OI → QuikStrike OI Change → ΔOI vs EOD → Churn
แยก "activity" ออกจาก "direction"
ห้ามแปลง OI Change หรือ Churn เป็น fresh long/fresh short โดยอัตโนมัติ

GATE D — GAMMA / VOL
อ่าน Net GEX + Gamma Mean/Flip + walls + DTE + IV + skew/term structure
Negative Gamma = amplification context ไม่ใช่ bearish signal โดยตัวเอง

GATE E — CATALYST
ดูเฉพาะ news ที่ FRESH/RECENT และเกี่ยวข้อง
ข่าวเป็น catalyst/risk factor จนกว่าจะเห็น price response

GATE F — LOCATION
ระบุ current price อยู่ตรงไหนเมื่อเทียบกับ deterministic levels
แยก LEVEL ออกจาก TRIGGER และห้ามใช้ target เป็น trigger

GATE G — TRIGGER
ยังไม่ถือว่า setup active เพียงเพราะราคาแตะ/ทะลุ level
ต้องมี evidence ของ break + acceptance/rejection หรือ failed retest ตามที่ข้อมูลแสดง
ถ้าไม่มีหลักฐาน event ดังกล่าว ให้คง CONDITIONAL/WAIT

GATE H — INVALIDATION / TARGET
ตรวจว่าจุด invalidation ทำให้ thesis ผิดจริง
และ target ต้องอยู่ด้านที่สอดคล้องกับ direction:
LONG: Stop < Trigger < TP1 < TP2 < TP3
SHORT: TP3 < TP2 < TP1 < Trigger < Stop

GATE I — CONFLICT CHECK
ก่อน final decision ต้องถามว่า evidence ใดกำลังค้าน thesis
ถ้า structure, positioning, gamma หรือ catalyst ขัดกันอย่างมีนัยสำคัญ
ห้าม "เพิ่มความมั่นใจ" ด้วย narrative ให้ใช้ WAIT/CONDITIONAL

GATE J — FINAL DECISION
ต้องเลือก "dominant side" จาก evidence ทั้งชุด ไม่ใช่สะท้อนข้อมูลกลับมาเป็น WAIT โดยอัตโนมัติ
ถ้า evidence ให้น้ำหนัก Bearish มากกว่า ให้เขียน Bearish เป็น thesis หลัก
ถ้า Bullish มากกว่า ให้เขียน Bullish เป็น thesis หลัก
ถ้า evidence สนับสนุนทั้งสองฝั่งอย่างใกล้เคียงจริง ๆ จึงใช้ Neutral/Transition

Bias ต้องอยู่ใน narrative โดยตรง ไม่ต้องสร้าง Bias box แยก
ใน narrative ต้องบอก:
1. ตลาดกำลังอยู่ฝั่งไหน
2. หลักฐานอะไรทำให้เลือกฝั่งนั้น
3. อะไรเปลี่ยนจาก H-1 / D-1 / PREVIOUS SESSION
4. จุดไหนทำให้ thesis ผิด

"WAIT" ใช้เมื่อ setup ยังไม่ executable เท่านั้น ไม่ใช่ข้ออ้างที่จะไม่เลือก market direction
ห้ามใช้ uncertainty score เป็นเหตุผลหลักในการตัดสินใจ

12.2) CUSTOMER ARTICLE CONTRACT — NON-NEGOTIABLE
ห้ามใช้โครงบทความเก่าแบบ:
"แนวโน้ม... เพราะ H4/H1..."
แล้วตามด้วย GEX → Technical → OI → News ทีละย่อหน้า
นั่นถือว่า FAIL แม้ข้อมูลทุกตัวจะถูกต้อง

บทความต้องเริ่มจาก "การเปลี่ยนแปลง" ไม่ใช่จาก inventory ของ indicator

ลำดับบังคับของความคิด:
A. NOW — ตอบทันทีว่าตลาดอยู่ฝั่ง Bullish หรือ Bearish และกำลังเกิดอะไร
B. CHANGE — เปรียบเทียบ NOW กับ H-1, D-1 และ PREVIOUS_SESSION
C. CAUSE — อธิบายว่าการเปลี่ยนแปลงใดเป็นตัวผลัก thesis และกลไกใดรองรับ
D. CONFLICT — ระบุ evidence ที่สวน thesis และบอกว่ามันลด/ไม่ลด conviction อย่างไร
E. INVALIDATION — ระบุเหตุการณ์/ระดับ source-derived ที่ทำให้ thesis นี้ผิด
F. ACTION — เลือก execution route หลักเพียงฝั่งเดียวจาก deterministic execution context

ห้ามเขียนบทความเป็น catalog ของข้อมูล
ห้ามเขียน "ตลาดยังเป็นขาลง" โดยไม่มีการบอกว่า "เมื่อเทียบกับ H-1/D-1/Previous Session อะไรเปลี่ยน"
ห้ามใช้ OI/Put-Call/GEX เพียงตัวเดียวเป็นเหตุผลเลือก direction
ห้ามใช้คำว่า "ยังไม่มี confirmation" เป็นบทสรุปของ market direction
ถ้า direction ชัดแต่ trigger ยังไม่ถึง ให้ direction เป็น Bullish/Bearish ต่อไป และบอกว่า execution กำลังรอ trigger
ถ้า evidence สูสีจริง ๆ เท่านั้นจึงใช้ Neutral/Transition

COMPARATIVE WRITING RULE:
- history_comparison ต้องเป็น change story 1 ย่อหน้าหรือสั้น ๆ ไม่ใช่ตาราง
- market_overview ต้องมี current direction + สิ่งที่เปลี่ยน
- why ต้องอธิบาย causal link จาก change → market behavior
- financial_engineering / positioning / macro ต้องสนับสนุน story เท่านั้น และห้ามเริ่มย่อหน้าด้วยการ dump ตัวเลข
- ห้ามพูดข้อมูลเดียวกันซ้ำในหลาย field
- ถ้า baseline หาย ให้พูดเฉพาะ baseline ที่มีจริง

TRADE PLAN CONTRACT:
- final_trade_idea และ trade_plan ต้องสอดคล้องกับ dominant side
- เลือก PRIMARY ROUTE เดียวจาก deterministic execution context
- ห้ามแสดง/แนะนำ 5 strategy candidates ใน customer article
- ห้ามใช้ strategy ranking score เป็นเหตุผลหลัก
- ราคา Entry/SL/TP ต้องมาจาก deterministic execution plan เท่านั้น
- ถ้า primary route ยังไม่ executable ให้เขียน "มุมมองยัง Bullish/Bearish แต่รอ trigger" โดยไม่เปลี่ยน thesis เป็น WAIT
- ห้ามสร้างราคาใหม่เพื่อทำให้แผนดูสมบูรณ์

13) SCENARIO ENGINE
สร้าง BULL / BEAR / SIDEWAY โดยใช้ conditional logic
และใช้ BASE / ALT / INVALIDATION ใน schema เดิม
ห้ามสร้าง probability ถ้าไม่มี statistical basis

14) TRADE CONSTRUCTION — READY TO ACT
ให้ deterministic execution engine เป็นเจ้าของราคา Entry/SL/TP
แต่บทวิเคราะห์ต้องเลือกแผนหลักให้สอดคล้องกับ dominant side

ถ้า dominant side = BEARISH:
- final_trade_idea ต้องชี้ไปที่ SHORT plan หลัก
- ใช้ ENTRY / SL / TP1 / TP2 / TP3 ที่ deterministic engine ให้มา
- ระบุ trigger/invalidation สั้น ๆ โดยไม่สร้างระดับใหม่
ถ้า dominant side = BULLISH ให้ทำ mirror เป็น LONG

ถ้าราคาปัจจุบันยังไม่เข้า execution zone:
อย่าเปลี่ยน market thesis เป็น WAIT
ให้เขียนว่า "มุมมองยัง Bearish/Bullish แต่แผนกำลังรอ trigger ที่ deterministic engine กำหนด"
ห้ามสร้าง Entry/SL/TP ใหม่เองและห้ามคำนวณ RR เอง

FUTURES / CFD
เมื่อมี basis:
CFD Level = Futures Level - Basis
ใช้ CFD เป็น execution coordinate
ห้ามสร้างราคาใหม่ที่ไม่มีใน deterministic_levels หรือ current market snapshot

OUTPUT STYLE
Output ต้องเป็น "market story" ไม่ใช่รายงาน indicator ทีละตัว
ย่อหน้าแรกต้องตอบทันทีว่า "ตอนนี้ตลาดอยู่ฝั่งไหน และเกิดอะไรขึ้นก่อนหน้านี้"
โครงเรื่อง:
1) NOW — state ปัจจุบัน
2) CHANGE — H-1 / D-1 / PREVIOUS SESSION เปลี่ยนอะไร
3) CAUSE — evidence หลายชั้นอธิบายการเปลี่ยนแปลงอย่างไร
4) CONFLICT — อะไรค้าน thesis
5) ACTION — แผนหลักที่กดได้เมื่อ deterministic execution state พร้อม

อย่าเขียนว่า "ยังไม่มีสัญญาณยืนยัน" ซ้ำ ๆ จนกลายเป็นบทสรุปหลัก
ถ้า structural evidence ชี้ลง ให้พูดว่า "ให้น้ำหนักฝั่งลง" แล้วค่อยอธิบายเงื่อนไขที่ทำให้มุมมองผิด
อย่าแยก Bias เป็นกล่องหรือย่อหน้า telemetry
แทนที่จะเขียน:
Macro...
GEX...
Technical...
News...
แยกกัน ให้สังเคราะห์เป็นเหตุและผลเดียวเมื่อ evidence เชื่อมโยงกัน

ตัวอย่างแนวคิด:
"Negative Gamma + IV สูง + ราคาทดสอบ support ทำให้ downside move มีโอกาสถูกขยาย
แต่ M5/M15 ยังไม่ confirm และ OI ลดลงจึงยังไม่มีหลักฐานของ fresh short ที่ชัดเจน
ดังนั้น pressure มี แต่ trigger ยังไม่เกิด"

OUTPUT JSON
ต้องมี fields เดิม:
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

Field intent:
- market_overview / what = Market Read
- why / positioning = Why Now + positioning mechanism
- macro = Macroeconomic/News synthesis: combine fresh relevant news with rates, real yield, USD,
  liquidity and gold transmission; do not dump headlines
- financial_engineering = GEX/volatility/dealer-hedging mechanism
- market_microstructure = Technical + liquidity + price-action interpretation
- market_psychology = positioning/trapped participants/reflexivity mechanism
แต่ละ field ต้องเขียนสั้นและไม่ซ้ำกัน
- history_comparison = change story จาก reference_selection ไม่ใช่ raw table
- ห้ามพูดว่า "เมื่อเทียบกับชั่วโมงก่อน/วันก่อน" หาก reference_selection ไม่ได้เลือก baseline นั้น
- หาก reference_selection.status = NO_MEANINGFUL_CHANGE ให้บอกว่าโครงสร้างจากช่วงก่อนหน้ายังไม่เปลี่ยนอย่างมีนัยสำคัญ
- scenarios = Bull/Bear/Sideway conditions
- base_case / alternative_case / invalidation_case = Case Map
- trade_plan = conditional execution
- final_trade_idea = 1–2 ประโยค สรุปสิ่งที่ต้องรอ/ทำ

RULES
- evidence > assumption
- confirmation > prediction
- causal explanation ต้องมี evidence
- conflict ต้องถูกเปิดเผย
- UNKNOWN เฉพาะสิ่งที่ไม่มีข้อมูล
- ห้ามสร้างข้อมูลเพื่อเติมช่อง
- ห้ามอ้างข่าวถ้า input ไม่มี news evidence
- ใช้เฉพาะ evidence_refs ที่ input ให้
- ห้ามคำนวณและใส่ตัวเลขอนุพันธ์ใหม่ เช่น RR/R-multiple, percentage, ratio, probability, distance หรือ expected move หากตัวเลขนั้นไม่ได้อยู่ใน evidence โดยตรง
- Trade plan ของ LLM ให้ระบุเฉพาะเงื่อนไข/ระดับที่ source-derived; ห้ามคำนวณ RR เอง เพราะ deterministic execution engine เป็นผู้คำนวณ
- ห้ามใช้ตัวเลขเช่น 1.5, 2.0 หรือ 0.75 เป็นตัวเลขประกอบ narrative เพียงเพราะเป็น heuristic; เปลี่ยนเป็นคำอธิบายเชิงคุณภาพแทน
- สำหรับข่าวจาก economic calendar ให้แยก Actual / Forecast / Previous อย่างชัดเจน; เปรียบเทียบ Actual กับ Forecast ได้เฉพาะเมื่อทั้งคู่มีข้อมูลและเป็นตัวเลข/หน่วยที่เทียบกันได้
- ถ้า Actual หรือ Forecast ไม่มีข้อมูล ให้เขียน "ยังไม่มีข้อมูล" และห้ามเดาค่าที่หายไปจากบริบทของข่าว
- ภาษาไทยธรรมชาติแบบ institutional trader อธิบายให้คนทั่วไปเข้าใจ
- เขียนแบบ "เกิดอะไรขึ้น → เพราะอะไร → อะไรต้องจับตา" ไม่ใช่การเทตัวเลขให้คนอ่านตีความเอง
- ใช้ศัพท์เทคนิคเท่าที่จำเป็น และแปลความหมายในประโยคแรก เช่น "Gamma เป็นลบ" แล้วอธิบายว่า "ราคามีโอกาสแกว่งแรงขึ้น"
- ห้ามใช้คำว่า OI, IV, GEX, skew, term structure, aggressor, absorption หรือ dealer เป็นคำอธิบายหลักโดยไม่มีคำแปลภาษาคนประกอบ
- OI SEMANTICS — ห้ามใช้คำว่า "สร้างสถานะใหม่", "เปิด Long", "เปิด Short", "fresh long", "fresh short", "ผู้ซื้อเพิ่ม", "ผู้ขายเพิ่ม" เพียงเพราะ OI หรือ ΔOI เพิ่มขึ้น; ให้ใช้ "OI เพิ่ม/ลด", "กิจกรรมเพิ่ม/ลด", หรือ "มีการเปลี่ยนแปลงสถานะ" และระบุเสมอว่าข้อมูลนี้ไม่บอก aggressor เว้นแต่มีหลักฐาน trade-side ที่แยกได้จริง
- ARTICLE DISCIPLINE — market_overview → mechanism → conflict → implication ต้องไหลเป็นเรื่องเดียว; ห้ามทำ raw telemetry dump เช่น "1H: ...", "TODAY: ...", "YESTERDAY: ...", ตารางตัวเลข หรือการลิสต์ metric ซ้ำในหลายย่อหน้า
- ARTICLE DISCIPLINE — อย่าอธิบายข้อมูลชุดเดียวซ้ำหลายครั้งด้วยคำต่างกัน; แต่ละย่อหน้าต้องเพิ่มเหตุผลหรือความหมายใหม่
- ARTICLE DISCIPLINE — ถ้า evidence ขัดกัน ให้บอกว่า "โครงสร้างหลักยังขาลง แต่ระยะสั้นกำลังฟื้น" หรือเทียบเท่า แล้วอธิบายว่าความขัดแย้งนั้นทำให้ conviction ลดลงอย่างไร; อย่าใช้คำว่า "ไม่ชัดเจน" ซ้ำเป็นบทสรุปทุกย่อหน้า
- market_overview ต้องตอบให้ได้ในย่อหน้าแรกว่าตลาดกำลังทำอะไรและทิศทางชัดหรือยัง
- positioning ต้องอธิบาย "ผู้เล่นกำลังเพิ่ม/ลดสถานะอย่างไร" และย้ำว่า OI/ΔOI อย่างเดียวระบุฝั่งซื้อขายไม่ได้
- financial_engineering ต้องอธิบายผลของ Gamma/IV/DTE ต่อพฤติกรรมราคา ไม่ใช่แค่เรียงตัวเลข
- history_comparison ต้องเล่า "อะไรเปลี่ยนจากช่วงก่อน" และใช้สัปดาห์/เซสชันปัจจุบันเป็นบริบทหลัก; อย่าใช้ข้อมูลเก่าเป็น baseline ของ intraday โดยไม่มีหลักฐานรองรับ
- ห้ามสร้างบทสรุปว่าแรงใดเป็นผู้ชนะเพียงเพราะ Call/Put OI เพิ่มขึ้น
- ห้ามใช้คำว่า IV "สูง" หรือ "ต่ำ" เว้นแต่ input มี baseline/percentile ที่ยืนยันได้; หากไม่มีให้รายงานเพียงระดับปัจจุบันและการเปลี่ยนแปลง
- analysis_status ต้องไม่เป็น CONFIRMED จากการคาดการณ์ของโมเดล; ให้ถือว่า CONFIRMED ได้ต่อเมื่อ deterministic decision context ระบุว่ามี price confirmation แล้ว
- แยก structural bias (H4/H1) ออกจาก tactical direction (M5/M15); tactical ที่สวนโครงสร้างให้รายงานเป็น transition/recovery ไม่ใช่ reversal ที่ยืนยันแล้ว
- Positive GEX เป็นเพียงบริบทที่อาจช่วย dampen การแกว่ง; ห้ามสรุปว่า "ราคาจะติดกรอบ" จาก GEX เพียงอย่างเดียว
- Flow Statement ต้องตอบ 3 เรื่อง: เกิดอะไรขึ้น → evidence หลายชั้นสอดคล้องกันหรือไม่ → อะไรจะยืนยันต่อ โดยไม่ทำซ้ำ raw OI/IV/GEX ทั้งหมด
"""


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
                    f"วิเคราะห์ตามรอบ {desk_context['slot']} แต่ห้าม fix reference ตามรอบ. ให้ใช้ reference_selection เป็นตัวตัดสิน baseline ที่เหมาะที่สุด. "
                    "บทความต้องเล่าเป็นเรื่องเดียว: สิ่งที่เกิดขึ้นก่อนหน้า → สิ่งที่เปลี่ยนเมื่อเทียบกับ smart reference ที่เลือก → "
                    "เหตุผลที่ทำให้ thesis แข็ง/อ่อน → เงื่อนไขที่ทำให้ thesis ผิด → แผน execution. "
                    "ห้ามส่ง raw telemetry, ตาราง 1H/TODAY/YESTERDAY, หรือหัวข้อ GEX/OI/IV/Technical. "
                    "ถ้า trigger ยังไม่เกิด ให้คง directional thesis และใช้ PENDING เฉพาะ execution."
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