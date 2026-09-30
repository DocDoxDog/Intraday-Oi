from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from quant.models import OIObservation
from quant.pit import require_available_at


def calculate_oi_change(current: OIObservation, previous: OIObservation | None) -> float | None:
    if previous is None:
        return None
    if current.option_type != previous.option_type:
        raise ValueError("OI_CHANGE_OPTION_TYPE_MISMATCH")
    if current.oi < 0 or previous.oi < 0:
        raise ValueError("OI_MUST_BE_NON_NEGATIVE")
    return float(current.oi - previous.oi)


def aggregate_oi(
    observations: Iterable[OIObservation],
    *,
    decision_time=None,
) -> dict:
    rows = list(observations)
    if decision_time is not None:
        rows = require_available_at(rows, decision_time)

    by_type = defaultdict(float)
    by_expiry = defaultdict(float)
    total_change = 0.0
    have_change = False

    for row in rows:
        by_type[row.option_type.value] += float(row.oi)
        by_expiry[row.expiration_id] += float(row.oi)
        if row.oi_change is not None:
            total_change += float(row.oi_change)
            have_change = True

    return {
        "count": len(rows),
        "call_oi": by_type["CALL"],
        "put_oi": by_type["PUT"],
        "total_oi": by_type["CALL"] + by_type["PUT"],
        "oi_change_total": total_change if have_change else None,
        "oi_by_expiration": dict(by_expiry),
    }
