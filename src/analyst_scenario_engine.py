"""Market Analyst V4 scenario engine.

Scenario-first deterministic layer. No LLM-created prices, no dealer-position inference,
and no order placement.
"""
from __future__ import annotations
from typing import Any

def _n(v: Any) -> float | None:
    if isinstance(v, bool) or v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

def _trend(state: dict[str, Any], tf: str) -> str:
    return str(((state.get("technical") or {}).get(tf) or {}).get("trend") or "").lower()

def _bos(state: dict[str, Any], tf: str) -> str:
    return str(((state.get("technical") or {}).get(tf) or {}).get("bos") or "").lower()

def _htf(state: dict[str, Any]) -> str:
    return str(((((state.get("decision_framework") or {}).get("steps") or {})
                 .get("1_market_state") or {}).get("htf_structure") or "mixed").lower())

def _market(state: dict[str, Any]) -> dict[str, Any]:
    return state.get("market_map") or {}

def _candidate_levels(state: dict[str, Any], side: str) -> list[float]:
    market = _market(state)
    key = "long_structural_levels" if side == "LONG" else "short_structural_levels"
    values = [_n(v) for v in (market.get(key) or [])]
    values = [v for v in values if v is not None]
    if values:
        return values
    keys = ("R1", "R2", "R3") if side == "LONG" else ("S1", "S2", "S3")
    return [v for v in (_n(market.get(k)) for k in keys) if v is not None]

def _invalidation(state: dict[str, Any], side: str, trigger: float | None) -> tuple[float | None, str]:
    technical = state.get("technical") or {}
    candidates: list[tuple[float, str]] = []
    for tf in ("m15", "h1", "h4"):
        ctx = technical.get(tf) or {}
        names = ("swing_low", "structure_low", "support", "low") if side == "LONG" else ("swing_high", "structure_high", "resistance", "high")
        for key in names:
            value = _n(ctx.get(key))
            if value is not None:
                candidates.append((value, f"{tf}.{key}"))
    valid = [x for x in candidates if trigger is not None and (x[0] < trigger if side == "LONG" else x[0] > trigger)]
    if valid:
        value, source = (max(valid, key=lambda x: x[0]) if side == "LONG" else min(valid, key=lambda x: x[0]))
        return value, "TECHNICAL_STRUCTURE:" + source
    fallback = _n(_market(state).get("short_trigger" if side == "LONG" else "long_trigger"))
    return (fallback, "OPPOSITE_OPTION_WALL_FALLBACK") if fallback is not None else (None, "UNKNOWN")

def _rr(side: str, entry: float | None, stop: float | None, target: float | None) -> float | None:
    if None in (entry, stop, target):
        return None
    risk = entry - stop if side == "LONG" else stop - entry
    reward = target - entry if side == "LONG" else entry - target
    if risk <= 0 or reward <= 0:
        return None
    return round(reward / risk, 2)

def _targets(side: str, trigger: float | None, stop: float | None, levels: list[float]) -> dict[str, Any]:
    if trigger is None or stop is None:
        return {"structural_path": levels, "execution_targets": [], "rr": [], "execution_eligible": False}
    ordered = [v for v in levels if (v > trigger if side == "LONG" else v < trigger)]
    pairs = [(v, _rr(side, trigger, stop, v)) for v in ordered]
    executable = [(v, rr) for v, rr in pairs if rr is not None and rr >= 1.0]
    return {
        "structural_path": ordered,
        "execution_targets": [v for v, _ in executable[:3]],
        "rr": [rr for _, rr in executable[:3]],
        "execution_eligible": bool(executable),
    }

def _confirmation(state: dict[str, Any], side: str) -> dict[str, Any]:
    htf, m15, m5, bos = _htf(state), _trend(state, "m15"), _trend(state, "m5"), _bos(state, "m5")
    if side == "LONG":
        conditions = {"htf": htf == "bullish", "m15": m15 == "bullish", "m5": m5 == "bullish",
                      "m5_bos": bos in {"bullish", "bull", "up", "bos_up", "break_up"}}
    else:
        conditions = {"htf": htf == "bearish", "m15": m15 == "bearish", "m5": m5 == "bearish",
                      "m5_bos": bos in {"bearish", "bear", "down", "bos_down", "break_down"}}
    return {"required": ["HTF alignment", "M15 alignment", "M5 alignment", "M5 BOS",
                         "acceptance/retest evidence when available"],
            "observed": conditions, "complete": all(conditions.values())}

def _status(state: dict[str, Any], side: str, trigger: float | None, confirmation: dict[str, Any]) -> str:
    current = _n((state.get("price") or {}).get("cfd"))
    if trigger is None or current is None:
        return "DATA_INSUFFICIENT"
    reached = current >= trigger if side == "LONG" else current <= trigger
    if not reached:
        return "ARMED"
    return "CONFIRMED" if confirmation["complete"] else "LEVEL_REACHED_WAIT_CONFIRMATION"

def build_market_scenarios(state: dict[str, Any]) -> dict[str, Any]:
    market, current = _market(state), _n((state.get("price") or {}).get("cfd"))
    long_trigger, short_trigger = _n(market.get("long_trigger")), _n(market.get("short_trigger"))
    result = {
        "version": "market-analyst-v4",
        "current_price": current,
        "context": {
            "gamma_mean": _n(market.get("pivot")),
            "positive_gamma_zone": _n(market.get("positive_gamma_zone")),
            "negative_gamma_zone": _n(market.get("negative_gamma_zone")),
            "note": "Gamma levels are context, not directional triggers or automatic targets.",
        },
        "scenarios": {},
    }
    for side, trigger, key in (("LONG", long_trigger, "long"), ("SHORT", short_trigger, "short")):
        stop, stop_source = _invalidation(state, side, trigger)
        structural = _candidate_levels(state, side)
        target_data = _targets(side, trigger, stop, structural)
        confirmation = _confirmation(state, side)
        status = _status(state, side, trigger, confirmation)
        result["scenarios"][key] = {
            "side": side, "status": status,
            "trigger": {"level": trigger, "condition": "acceptance beyond trigger",
                        "source": "STRUCTURAL_OPTION_WALL"},
            "confirmation": confirmation,
            "invalidation": {"level": stop, "source": stop_source},
            "structural_path": target_data["structural_path"],
            "execution_targets": target_data["execution_targets"],
            "rr": target_data["rr"],
            "execution_eligible": target_data["execution_eligible"],
            "execution_block_reason": None if target_data["execution_eligible"] else "NO_TARGET_GE_1R",
        }
    inside = current is not None and short_trigger is not None and long_trigger is not None and short_trigger < current < long_trigger
    result["range"] = {"status": "ACTIVE" if inside else "INACTIVE", "lower": short_trigger, "upper": long_trigger,
                       "condition": "remain inside structural band until one side resolves"}
    result["decision"] = _overall_decision(result)
    return result

def _overall_decision(result: dict[str, Any]) -> dict[str, Any]:
    bull, bear = result["scenarios"]["long"], result["scenarios"]["short"]
    confirmed = [x for x in (bull, bear) if x["status"] == "CONFIRMED"]
    reached = [x for x in (bull, bear) if x["status"] == "LEVEL_REACHED_WAIT_CONFIRMATION"]
    if len(confirmed) == 1:
        return {"state": "DIRECTIONAL_CONFIRMATION", "side": confirmed[0]["side"],
                "reason": "trigger and deterministic confirmation are aligned"}
    if reached:
        return {"state": "WAIT_CONFIRMATION", "side": reached[0]["side"] if len(reached) == 1 else "BOTH",
                "reason": "structural level reached but confirmation is incomplete"}
    if bull["status"] == "ARMED" and bear["status"] == "ARMED":
        return {"state": "RANGE_OR_BREAKOUT_WAIT", "side": "NONE",
                "reason": "both scenarios remain conditional"}
    return {"state": "DATA_INSUFFICIENT", "side": "NONE", "reason": "required structural evidence is missing"}
