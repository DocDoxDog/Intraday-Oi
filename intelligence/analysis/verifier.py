from __future__ import annotations

import re
from dataclasses import dataclass


_NUM = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?")


@dataclass(frozen=True)
class VerificationResult:
    ok: bool
    violations: tuple[str, ...]


def verify_output(
    text: str,
    *,
    allowed_numbers: set[float],
    source_urls: set[str],
    required_metadata: dict[str, object],
) -> VerificationResult:
    violations: list[str] = []

    for token in _NUM.findall(text or ""):
        try:
            value = float(token)
        except ValueError:
            continue
        if not any(abs(value - allowed) <= 1e-9 for allowed in allowed_numbers):
            violations.append(f"UNSUPPORTED_NUMBER:{token}")

    if "http://" in text or "https://" in text:
        urls = set(re.findall(r"https?://\S+", text))
        if not urls.intersection(source_urls):
            violations.append("UNSUPPORTED_SOURCE_URL")

    required_keys = {
        "as_of",
        "data_age",
        "data_quality",
        "dataset_version",
        "calculation_version",
        "assumptions",
    }
    missing = sorted(
        k for k in required_keys
        if required_metadata.get(k) is None
        or required_metadata.get(k) == ""
        or required_metadata.get(k) == ()
    )
    violations.extend(f"MISSING_METADATA:{key}" for key in missing)

    forbidden = (
        "100% guaranteed",
        "guaranteed profit",
        "must buy",
        "must sell",
    )
    lower = (text or "").lower()
    violations.extend(f"FORBIDDEN_LANGUAGE:{phrase}" for phrase in forbidden if phrase in lower)

    return VerificationResult(ok=not violations, violations=tuple(violations))


def verify_market_analysis(analysis, *, market_state, source_urls: set[str] = ()) -> VerificationResult:
    """Verify a structured analysis before customer delivery."""
    violations: list[str] = []
    allowed_numbers = {
        float(x)
        for x in (
            market_state.price,
            market_state.oi,
            market_state.oi_change,
            market_state.gex,
            market_state.dex,
            market_state.iv,
            market_state.realized_vol,
            market_state.gamma_flip,
            market_state.call_wall,
            market_state.put_wall,
        )
        if x is not None
    }
    for level in analysis.key_levels:
        if not any(abs(float(level) - allowed) <= 1e-9 for allowed in allowed_numbers):
            violations.append(f"UNSUPPORTED_LEVEL:{level}")
    required = {
        "as_of": market_state.as_of.isoformat(),
        "data_age": market_state.data_age_seconds,
        "data_quality": market_state.data_quality,
        "dataset_version": market_state.dataset_version,
        "calculation_version": market_state.calculation_version,
        "assumptions": market_state.assumptions,
    }
    text = " ".join(
        (analysis.market_context, analysis.what_changed, analysis.why_it_matters)
        + tuple(analysis.evidence)
    )
    base = verify_output(
        text,
        allowed_numbers=allowed_numbers,
        source_urls=source_urls,
        required_metadata=required,
    )
    violations.extend(base.violations)
    return VerificationResult(ok=not violations, violations=tuple(violations))


def verify_scenario_plan(plan, *, market_state) -> VerificationResult:
    allowed_numbers = {
        float(x)
        for x in (
            market_state.price,
            market_state.gamma_flip,
            market_state.call_wall,
            market_state.put_wall,
        )
        if x is not None
    }
    violations: list[str] = []
    for level in plan.key_levels:
        if not any(abs(float(level) - allowed) <= 1e-9 for allowed in allowed_numbers):
            violations.append(f"UNSUPPORTED_LEVEL:{level}")
    text = " ".join(
        tuple(plan.trigger)
        + tuple(plan.confirmation)
        + tuple(plan.invalidation)
        + tuple(plan.risk_factors)
    )
    base = verify_output(
        text,
        allowed_numbers=allowed_numbers,
        source_urls=set(),
        required_metadata={
            "as_of": market_state.as_of.isoformat(),
            "data_age": market_state.data_age_seconds,
            "data_quality": market_state.data_quality,
            "dataset_version": market_state.dataset_version,
            "calculation_version": market_state.calculation_version,
            "assumptions": market_state.assumptions,
        },
    )
    violations.extend(base.violations)
    return VerificationResult(ok=not violations, violations=tuple(violations))
