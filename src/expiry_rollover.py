"""Expiry-term intelligence: Friday series, monthly roll-over, and roll pressure.

The engine is deliberately conservative:
- current term-structure comparisons are called *rollover pressure*, never confirmed
  rollover, because one snapshot cannot prove that positions were transferred;
- confirmed transfer requires repeated observations of the same expiry and strike;
- missing next-month/Friday data remains UNKNOWN;
- no synthetic OI/GEX is created.

Gold weekly expiry conventions follow CME's OG1-OG5 Friday weekly series and the
G1M/G1T/G1W/G1R daily families. Month letters follow CME month codes.
"""

from __future__ import annotations

from typing import Any
import re

MONTH_CODES = ("F", "G", "H", "J", "K", "M", "N", "Q", "U", "V", "X", "Z")
MONTH_INDEX = {c: i for i, c in enumerate(MONTH_CODES, start=1)}

_FRIDAY_RE = re.compile(r"^OG(?P<week>[1-5])(?P<month>[FGHJKMNQUVXZ])(?P<year>\\d)$", re.I)
_DAILY_RE = re.compile(r"^G(?P<week>[1-5])(?P<weekday>[MTWR])(?P<month>[FGHJKMNQUVXZ])(?P<year>\\d)$", re.I)
_MONTHLY_RE = re.compile(r"^OG(?P<month>[FGHJKMNQUVXZ])(?P<year>\\d)$", re.I)


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) else None


def classify_expiry(code: str | None) -> dict[str, Any]:
    code = str(code or "").strip().upper()
    if not code:
        return {"code": code, "kind": "UNKNOWN", "weekday": None, "week": None}

    m = _FRIDAY_RE.match(code)
    if m:
        return {
            "code": code,
            "kind": "WEEKLY",
            "weekday": "FRIDAY",
            "week": int(m.group("week")),
            "month_code": m.group("month").upper(),
            "year_digit": int(m.group("year")),
            "is_friday": True,
        }

    m = _DAILY_RE.match(code)
    if m:
        weekday = {"M": "MONDAY", "T": "TUESDAY", "W": "WEDNESDAY", "R": "THURSDAY"}[m.group("weekday").upper()]
        return {
            "code": code,
            "kind": "WEEKLY",
            "weekday": weekday,
            "week": int(m.group("week")),
            "month_code": m.group("month").upper(),
            "year_digit": int(m.group("year")),
            "is_friday": False,
        }

    m = _MONTHLY_RE.match(code)
    if m:
        return {
            "code": code,
            "kind": "MONTHLY",
            "weekday": None,
            "week": None,
            "month_code": m.group("month").upper(),
            "year_digit": int(m.group("year")),
            "is_friday": False,
        }

    return {"code": code, "kind": "UNKNOWN", "weekday": None, "week": None}


def _snapshot_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    raw = snapshot.get("raw_series") or {}
    return [
        row for row in (raw.get("strike_rows") or snapshot.get("strike_rows") or [])
        if isinstance(row, dict) and _num(row.get("strike")) is not None
    ]


def _oi_totals(snapshot: dict[str, Any]) -> dict[str, Any]:
    rows = _snapshot_rows(snapshot)
    call = sum(float(r.get("oiCall") or 0) for r in rows if _num(r.get("oiCall")) is not None)
    put = sum(float(r.get("oiPut") or 0) for r in rows if _num(r.get("oiPut")) is not None)
    known_call = any(_num(r.get("oiCall")) is not None for r in rows)
    known_put = any(_num(r.get("oiPut")) is not None for r in rows)
    return {
        "call_oi": call if known_call else None,
        "put_oi": put if known_put else None,
        "total_oi": (call + put) if known_call or known_put else None,
    }


def _gex_total(snapshot: dict[str, Any]) -> float | None:
    raw = snapshot.get("raw_series") or {}
    gex = raw.get("gex") or {}
    value = _num(gex.get("net_gex"))
    if value is not None:
        return value
    rows = _snapshot_rows(snapshot)
    values = [_num(r.get("net_gex")) for r in rows]
    values = [v for v in values if v is not None]
    return sum(values) if values else None


def _snapshot_code(snapshot: dict[str, Any]) -> str:
    raw = snapshot.get("raw_series") or {}
    selection = raw.get("expiration_selection") or snapshot.get("expiration_selection") or {}
    return str(
        snapshot.get("expiration_code")
        or selection.get("selected")
        or raw.get("expiration_code")
        or ""
    ).strip().upper()


def _score_transfer(front: dict[str, Any], nxt: dict[str, Any]) -> dict[str, Any]:
    a = _oi_totals(front)
    b = _oi_totals(nxt)
    components: list[float] = []
    evidence: list[str] = []

    if a["total_oi"] not in (None, 0) and b["total_oi"] is not None:
        ratio = b["total_oi"] / a["total_oi"]
        components.append(min(1.0, ratio))
        evidence.append(f"NEXT_OI/FRONT_OI={ratio:.2f}")
    if a["call_oi"] not in (None, 0) and b["call_oi"] is not None:
        components.append(min(1.0, b["call_oi"] / a["call_oi"]))
    if a["put_oi"] not in (None, 0) and b["put_oi"] is not None:
        components.append(min(1.0, b["put_oi"] / a["put_oi"]))

    if not components:
        return {"status": "UNKNOWN", "score": None, "evidence": evidence}

    # This is a term-structure pressure score, not a probability.
    score = round(100.0 * sum(components) / len(components), 2)
    return {"status": "CANDIDATE", "score": score, "evidence": evidence}


def _overlap_concentration(front: dict[str, Any], nxt: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    def by_strike(s: dict[str, Any]) -> dict[float, float]:
        out: dict[float, float] = {}
        for r in _snapshot_rows(s):
            strike = _num(r.get("strike"))
            c = _num(r.get("oiCall"))
            p = _num(r.get("oiPut"))
            if strike is None or (c is None and p is None):
                continue
            out[strike] = float(c or 0) + float(p or 0)
        return out

    a, b = by_strike(front), by_strike(nxt)
    common = []
    for strike in set(a) & set(b):
        if a[strike] <= 0:
            continue
        common.append({
            "strike": strike,
            "front_oi": a[strike],
            "next_oi": b[strike],
            "next_front_ratio": round(b[strike] / a[strike], 3),
        })
    common.sort(key=lambda x: (x["next_front_ratio"], x["next_oi"]), reverse=True)
    return common[:limit]


def build_expiry_rollover_context(
    snapshots: list[dict[str, Any]],
    *,
    current_price: float | None = None,
    rollover_dte_threshold: float = 5.0,
) -> dict[str, Any]:
    """Build a point-in-time expiry/roll context from real observed snapshots."""

    observed: list[dict[str, Any]] = []
    for s in snapshots:
        code = _snapshot_code(s)
        if not code:
            continue
        info = classify_expiry(code)
        observed.append({
            "code": code,
            "dte": _num(s.get("dte")) or _num((s.get("raw_series") or {}).get("dte")),
            "kind": info["kind"],
            "weekday": info["weekday"],
            "week": info["week"],
            "is_friday": info.get("is_friday", False),
            "month_code": info.get("month_code"),
            "year_digit": info.get("year_digit"),
            "oi": _oi_totals(s),
            "gex": _gex_total(s),
            "_snapshot": s,
        })

    observed.sort(key=lambda x: (x["dte"] is None, x["dte"] if x["dte"] is not None else 999999, x["code"]))
    weekly_friday = [x for x in observed if x["kind"] == "WEEKLY" and x["is_friday"]]
    monthly = [x for x in observed if x["kind"] == "MONTHLY"]

    front = observed[0] if observed else None
    friday_front = weekly_friday[0] if weekly_friday else None
    friday_next = weekly_friday[1] if len(weekly_friday) > 1 else None
    monthly_front = monthly[0] if monthly else None
    monthly_next = monthly[1] if len(monthly) > 1 else None

    friday_roll = None
    if friday_front and friday_next:
        friday_roll = _score_transfer(friday_front["_snapshot"], friday_next["_snapshot"])
        friday_roll["front_code"] = friday_front["code"]
        friday_roll["next_code"] = friday_next["code"]
        friday_roll["overlap_concentration"] = _overlap_concentration(
            friday_front["_snapshot"], friday_next["_snapshot"]
        )
    elif friday_front:
        friday_roll = {
            "status": "WATCH",
            "score": None,
            "front_code": friday_front["code"],
            "next_code": None,
            "reason": "NEXT_FRIDAY_SERIES_NOT_OBSERVED",
            "overlap_concentration": [],
        }

    monthly_roll = None
    if monthly_front and monthly_next:
        monthly_roll = _score_transfer(monthly_front["_snapshot"], monthly_next["_snapshot"])
        monthly_roll["front_code"] = monthly_front["code"]
        monthly_roll["next_code"] = monthly_next["code"]
        monthly_roll["overlap_concentration"] = _overlap_concentration(
            monthly_front["_snapshot"], monthly_next["_snapshot"]
        )
    elif monthly_front:
        monthly_roll = {
            "status": "WATCH" if (monthly_front["dte"] is None or monthly_front["dte"] <= rollover_dte_threshold) else "NOT_ACTIVE",
            "score": None,
            "front_code": monthly_front["code"],
            "next_code": None,
            "reason": "NEXT_MONTHLY_SERIES_NOT_OBSERVED",
            "overlap_concentration": [],
        }

    return {
        "version": "expiry-rollover-v1",
        "status": "VALID" if observed else "UNKNOWN",
        "current_price": current_price,
        "front": {k: v for k, v in (front or {}).items() if k != "_snapshot"},
        "friday_series": [
            {k: v for k, v in x.items() if k != "_snapshot"}
            for x in weekly_friday[:5]
        ],
        "monthly_series": [
            {k: v for k, v in x.items() if k != "_snapshot"}
            for x in monthly[:4]
        ],
        "rollover": {
            "friday": friday_roll,
            "monthly": monthly_roll,
            "confirmed": False,
            "confirmation_rule": "requires_same_expiry_strike_observations_across_multiple_timestamps",
        },
        "limitations": [
            "single_snapshot_term_structure_is_pressure_not_confirmed_roll",
            "missing_next_series_remains_unknown",
            "oi_does_not_identify_aggressor_side",
        ],
    }
