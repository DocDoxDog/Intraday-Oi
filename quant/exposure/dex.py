from __future__ import annotations

from typing import Any


def _num(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def calculate_dex(
    rows,
    *,
    multiplier: float = 100.0,
    sign_convention: str = "OPTION_DELTAS",
) -> dict:
    out = []
    net = 0.0
    gross = 0.0
    dex_by_expiration: dict[str, dict[str, float]] = {}

    for raw in rows:
        call_oi = _num(raw.get("oiCall")) or 0.0
        put_oi = _num(raw.get("oiPut")) or 0.0
        call_delta = _num(raw.get("callDelta"))
        put_delta = _num(raw.get("putDelta"))
        if call_delta is None and put_delta is None:
            continue
        call_dex = call_oi * (call_delta or 0.0) * multiplier
        put_dex = put_oi * (put_delta or 0.0) * multiplier
        row = dict(raw)
        row.update(
            call_dex=call_dex,
            put_dex=put_dex,
            net_dex=call_dex + put_dex,
        )
        out.append(row)
        net += call_dex + put_dex
        gross += abs(call_dex) + abs(put_dex)
        expiry = str(raw.get("expiration_id") or "UNSPECIFIED")
        bucket = dex_by_expiration.setdefault(expiry, {"net_dex": 0.0, "call_dex": 0.0, "put_dex": 0.0})
        bucket["net_dex"] += call_dex + put_dex
        bucket["call_dex"] += call_dex
        bucket["put_dex"] += put_dex

    return {
        "status": "ok" if out else "unavailable",
        "contract_multiplier": multiplier,
        "sign_convention": sign_convention,
        "unit": "delta-equivalent contracts",
        "net_dex": net,
        "gross_dex": gross,
        "dex_by_expiration": dex_by_expiration,
        "expiry_count": len(dex_by_expiration),
        "rows": out,
    }
