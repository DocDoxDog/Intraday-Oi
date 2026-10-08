"""Canonical multi-expiration options state and gamma matrix.

This module does not infer missing values. It converts parsed QuikStrike
expiration snapshots into one deterministic term-structure matrix keyed by
real expiration identity.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExpirationIdentity:
    code: str
    dte: float | None
    observed_at: str | None = None

    def key(self) -> str:
        return self.code.upper().strip()


def _num(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _expiry_from_snapshot(snapshot: dict[str, Any]) -> ExpirationIdentity:
    raw = snapshot.get("raw_series") or {}
    selection = raw.get("expiration_selection") or snapshot.get("expiration_selection") or {}
    code = (
        snapshot.get("expiration_code")
        or selection.get("selected")
        or raw.get("expiration_code")
        or ""
    )
    code = str(code).strip()
    if not code:
        raise ValueError("EXPIRATION_IDENTITY_UNRESOLVED")
    dte = _num(snapshot.get("dte"))
    if dte is None:
        dte = _num(raw.get("dte"))
    return ExpirationIdentity(
        code=code,
        dte=dte,
        observed_at=snapshot.get("observed_at") or raw.get("observed_at"),
    )


def _rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    raw = snapshot.get("raw_series") or {}
    rows = raw.get("strike_rows") or snapshot.get("strike_rows") or []
    return [row for row in rows if isinstance(row, dict) and _num(row.get("strike")) is not None]


def build_gamma_matrix(
    snapshots: list[dict[str, Any]],
    *,
    current_price: float | None = None,
) -> dict[str, Any]:
    """Build a deterministic multi-expiry gamma matrix.

    Cell values come only from source-derived net_gex. Missing cells stay None.
    The caller is responsible for ordering snapshots chronologically.
    """

    expirations: dict[str, dict[str, Any]] = {}
    cells: dict[str, dict[str, float | None]] = {}

    for snapshot in snapshots:
        identity = _expiry_from_snapshot(snapshot)
        key = identity.key()
        exp = expirations.setdefault(
            key,
            {
                "code": identity.code,
                "dte": identity.dte,
                "observed_at": identity.observed_at,
            },
        )
        if identity.dte is not None:
            exp["dte"] = identity.dte
        if identity.observed_at:
            exp["observed_at"] = identity.observed_at

        for row in _rows(snapshot):
            strike = _num(row.get("strike"))
            if strike is None:
                continue
            strike_key = str(int(strike)) if strike.is_integer() else str(strike)
            cells.setdefault(strike_key, {})[key] = _num(row.get("net_gex"))

    ordered_expirations = sorted(
        expirations.values(),
        key=lambda x: (
            x["dte"] is None,
            x["dte"] if x["dte"] is not None else float("inf"),
            x["code"],
        ),
    )

    columns = [
        {
            "code": exp["code"],
            "dte": exp["dte"],
            "observed_at": exp["observed_at"],
        }
        for exp in ordered_expirations
    ]

    strikes = sorted(float(k) for k in cells)
    matrix = []
    for strike in strikes:
        strike_key = str(int(strike)) if strike.is_integer() else str(strike)
        row = {"strike": strike}
        for exp in columns:
            row[exp["code"]] = cells.get(strike_key, {}).get(exp["code"])
        matrix.append(row)

    totals = {}
    for exp in columns:
        values = [
            value for value in (row.get(exp["code"]) for row in matrix)
            if isinstance(value, (int, float))
        ]
        # No observations is UNKNOWN, not numeric zero.
        totals[exp["code"]] = sum(values) if values else None

    return {
        "version": "gamma-matrix-v1",
        "current_price": current_price,
        "columns": columns,
        "strikes": strikes,
        "matrix": matrix,
        "totals": totals,
        "observation_count": len(snapshots),
        "expiration_count": len(columns),
        "status": "VALID" if columns and matrix else "PARTIAL",
    }


def _median_spacing(values: list[float]) -> float:
    gaps = [
        round(values[i] - values[i - 1], 8)
        for i in range(1, len(values))
        if values[i] > values[i - 1]
    ]
    if not gaps:
        return 5.0
    gaps.sort()
    mid = len(gaps) // 2
    return gaps[mid] if len(gaps) % 2 else (gaps[mid - 1] + gaps[mid]) / 2.0


def select_structural_nodes(
    concentrations: list[tuple[float, float]],
    *,
    current: float | None,
    side: str,
    limit: int = 5,
    grid_strikes: list[float] | None = None,
) -> list[float]:
    """Select real structural strikes using local prominence, not a global 20% cutoff.

    A large distant concentration must not erase a smaller but locally important
    node near current price. The function still never creates synthetic prices.
    """
    if not concentrations:
        return []
    observed=sorted(set(float(x) for x in (grid_strikes or [s for s,_ in concentrations])))
    spacing=_median_spacing(observed)
    min_gap=max(5.0, 1.5*spacing)
    values=[abs(float(v)) for _,v in concentrations if v is not None]
    if not values: return []
    # Robust global noise floor. MAD is deliberately soft; it ranks candidates
    # rather than hard-filtering them.
    med=sorted(values)[len(values)//2]
    deviations=sorted(abs(v-med) for v in values)
    mad=deviations[len(deviations)//2] if deviations else 0.0
    floor=max(0.0, med + 2.0*mad)
    candidates=[]
    for strike,value in concentrations:
        strike=float(strike); magnitude=abs(float(value))
        if current is not None and ((side=="UP" and strike<=current) or (side!="UP" and strike>=current)):
            continue
        local=[]
        for s,v in concentrations:
            s=float(s)
            if abs(s-strike) <= max(spacing*2.0,10.0):
                local.append(abs(float(v)))
        local_peak=max(local,default=magnitude)
        prominence=(magnitude/(local_peak or 1.0))
        # Preserve strong local barriers even when they are below the largest
        # global concentration. Tier is based on evidence strength.
        tier=0 if magnitude >= max(floor, 0.50*max(values)) else (1 if prominence>=0.80 else 2)
        candidates.append((tier,-prominence,-magnitude,abs(strike-(current or strike)),strike))
    candidates.sort()
    selected=[]
    for _,_,_,_,strike in candidates:
        if all(abs(strike-picked)>=min_gap for picked in selected):
            selected.append(strike)
        if len(selected)>=limit: break
    return sorted(selected)


def summarize_gamma_zones(gamma_matrix: dict[str, Any]) -> dict[str, Any]:
    """Extract deterministic structural concentration nodes from real strikes."""

    matrix = gamma_matrix.get("matrix") or []
    columns = gamma_matrix.get("columns") or []
    current = _num(gamma_matrix.get("current_price"))

    aggregate: list[tuple[float, float]] = []
    for row in matrix:
        values = [
            _num(row.get(col["code"]))
            for col in columns
            if _num(row.get(col["code"])) is not None
        ]
        if values:
            aggregate.append((float(row["strike"]), sum(values)))

    positive = sorted(
        (item for item in aggregate if item[1] > 0),
        key=lambda item: item[1],
        reverse=True,
    )
    negative = sorted(
        (item for item in aggregate if item[1] < 0),
        key=lambda item: abs(item[1]),
        reverse=True,
    )

    observed_strikes = [
        float(row["strike"]) for row in matrix
        if _num(row.get("strike")) is not None
    ]
    resistance_nodes = select_structural_nodes(
        positive, current=current, side="UP", grid_strikes=observed_strikes
    )
    support_nodes = select_structural_nodes(
        negative, current=current, side="DOWN", grid_strikes=observed_strikes
    )

    return {
        "current_price": current,
        "highest_positive_gamma": positive[0][0] if positive else None,
        "highest_negative_gamma": negative[0][0] if negative else None,
        "resistance_nodes": resistance_nodes,
        "support_nodes": support_nodes,
        "positive_concentrations": [
            {"strike": strike, "aggregate_gex": value} for strike, value in positive[:10]
        ],
        "negative_concentrations": [
            {"strike": strike, "aggregate_gex": value} for strike, value in negative[:10]
        ],
        "selection_method": "magnitude_threshold_20pct_plus_strike_spacing_non_max_suppression",
        "status": "VALID" if aggregate else "UNKNOWN",
    }



_BANGKOK_OFFSET_HOURS = 7
_GOLD_MONTH_CODES = ("F", "G", "H", "J", "K", "M", "N", "Q", "U", "V", "X", "Z")


def build_gold_weekly_series_window(as_of: str | None = None, count: int = 7) -> list[dict[str, Any]]:
    """Build the expected next Gold weekly expiry identities from CME's naming convention.

    CME Gold weeklies use G1M..G5M (Mon), G1T..G5T (Tue),
    G1W..G5W (Wed), G1R..G5R (Thu) and OG1..OG5 (Fri), with the
    futures month/year suffix on the listed contract code. This helper only
    builds calendar identities; it never fabricates OI/GEX cells.
    """
    from datetime import datetime, timedelta, timezone

    if count < 1:
        return []
    if as_of:
        dt = datetime.fromisoformat(str(as_of).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone(timedelta(hours=_BANGKOK_OFFSET_HOURS)))
    else:
        dt = datetime.now(timezone(timedelta(hours=_BANGKOK_OFFSET_HOURS)))

    day = dt.date()
    out: list[dict[str, Any]] = []
    while len(out) < count:
        if day.weekday() < 5:
            week_number = ((day.day - 1) // 7) + 1
            weekday_map = {
                0: ("G", "M", "Monday"),
                1: ("G", "T", "Tuesday"),
                2: ("G", "W", "Wednesday"),
                3: ("G", "R", "Thursday"),
                4: ("OG", "V", "Friday"),
            }
            prefix, day_code, weekday_name = weekday_map[day.weekday()]
            month_code = _GOLD_MONTH_CODES[day.month - 1]
            year_digit = str(day.year % 10)
            code = f"{prefix}{week_number}{month_code}{year_digit}"
            out.append({
                "code": code,
                "expiry_date": day.isoformat(),
                "weekday": weekday_name,
                "weekday_short": day.strftime("%a"),
                "week_number": week_number,
                "calendar_days_from_as_of": (day - dt.date()).days,
                "status": "EXPECTED",
            })
        day += timedelta(days=1)
    return out


def merge_expected_expirations(
    gamma_matrix: dict[str, Any],
    *,
    as_of: str | None = None,
    count: int = 7,
) -> dict[str, Any]:
    """Keep the display focused on real observed expirations.

    Expected calendar identities are retained separately for the analyst and
    future collection, but the user-facing Gamma Table never allocates wide
    empty columns for unobserved series.
    """
    expected = build_gold_weekly_series_window(as_of=as_of, count=count)
    existing = {
        str(col.get("code")).upper(): dict(col)
        for col in (gamma_matrix.get("columns") or [])
        if str(col.get("code") or "").strip()
    }

    ordered_existing = sorted(
        existing.values(),
        key=lambda col: (
            col.get("dte") is None,
            col.get("dte") if isinstance(col.get("dte"), (int, float)) else float("inf"),
            str(col.get("code") or ""),
        ),
    )
    observed_columns = [
        dict(col, status="OBSERVED")
        for col in ordered_existing
    ]
    display_columns = observed_columns[: max(1, int(count))]

    observed_codes = [str(col["code"]).upper() for col in observed_columns]
    row_values = {
        str(int(float(r["strike"]))) if float(r["strike"]).is_integer() else str(float(r["strike"])): r
        for r in (gamma_matrix.get("matrix") or [])
    }
    matrix: list[dict[str, Any]] = []
    for strike_key in sorted(row_values, key=float, reverse=True):
        base = dict(row_values[strike_key])
        for col in observed_columns:
            base.setdefault(col["code"], None)
        matrix.append(base)

    totals: dict[str, float | None] = {}
    for col in observed_columns:
        values = [
            row.get(col["code"]) for row in matrix
            if isinstance(row.get(col["code"]), (int, float))
        ]
        totals[col["code"]] = sum(values) if values else None

    expected_missing = [
        item for item in expected
        if item["code"].upper() not in observed_codes
    ]

    out = dict(gamma_matrix)
    out.update({
        "columns": observed_columns,
        "display_columns": display_columns,
        "matrix": matrix,
        "totals": totals,
        "expected_expirations": expected,
        "missing_expected_expirations": expected_missing,
        "expected_expiration_count": len(expected),
        "observed_expiration_count": len(observed_columns),
        "expiration_count": len(observed_columns),
        "display_complete": len(display_columns) >= count,
        "status": "VALID" if matrix and observed_columns else "PARTIAL",
    })
    return out

