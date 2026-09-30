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
    missing = sorted(k for k in required_keys if not required_metadata.get(k))
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
