from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VerificationResult:
    ok: bool
    violations: tuple[str, ...] = ()


def verify_market_analysis(analysis: Any, *, market_state: Any) -> VerificationResult:
    """Verify AI-proposed levels against the deterministic state supplied upstream."""
    violations: list[str] = []
    known_levels = set()
    for key in ("gamma_flip", "call_wall", "put_wall"):
        value = getattr(market_state, key, None)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            known_levels.add(float(value))
    for value in getattr(analysis, "key_levels", ()) or ():
        try:
            level = float(value)
        except (TypeError, ValueError):
            violations.append("INVALID_KEY_LEVEL")
            continue
        if not any(abs(level - known) <= 1e-6 for known in known_levels):
            violations.append("UNKNOWN_KEY_LEVEL")
    confidence = getattr(analysis, "confidence", None)
    if confidence is not None:
        try:
            confidence_value = float(confidence)
            if not 0.0 <= confidence_value <= 1.0:
                violations.append("INVALID_CONFIDENCE")
        except (TypeError, ValueError):
            violations.append("INVALID_CONFIDENCE")
    return VerificationResult(ok=not violations, violations=tuple(violations))
