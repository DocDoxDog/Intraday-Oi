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


def summarize_gamma_zones(gamma_matrix: dict[str, Any]) -> dict[str, Any]:
    """Extract deterministic concentration zones without inventing levels."""

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

    return {
        "current_price": current,
        "highest_positive_gamma": positive[0][0] if positive else None,
        "highest_negative_gamma": negative[0][0] if negative else None,
        "positive_concentrations": [
            {"strike": strike, "aggregate_gex": value} for strike, value in positive[:10]
        ],
        "negative_concentrations": [
            {"strike": strike, "aggregate_gex": value} for strike, value in negative[:10]
        ],
        "status": "VALID" if aggregate else "UNKNOWN",
    }
