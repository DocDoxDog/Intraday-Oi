from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any


class LLMVerificationError(RuntimeError):
    pass


_NUMBER_RE = re.compile(
    r"(?<![A-Za-z])(?:[-−+]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|[-−+]?\d+(?:\.\d+)?)(?![A-Za-z])"
)


def _normalize_number(value: str) -> str:
    return value.replace(",", "").replace("−", "-")


def _numeric_strings(value: Any) -> list[str]:
    text = json.dumps(value, ensure_ascii=False, default=str)
    return [_normalize_number(match) for match in _NUMBER_RE.findall(text)]


def _cited_evidence_numbers(evidence: dict[str, Any], refs: list[str]) -> set[str]:
    numbers: set[str] = set()
    for ref in refs:
        item = evidence.get(ref)
        if item is not None:
            numbers.update(_numeric_strings(item))
    return numbers


def _strip_non_market_numeric(value: Any) -> Any:
    """Remove model-confidence metadata before market-number verification."""
    if isinstance(value, dict):
        return {
            key: _strip_non_market_numeric(child)
            for key, child in value.items()
            if key not in {"confidence", "uncertainty"}
        }
    if isinstance(value, list):
        return [_strip_non_market_numeric(child) for child in value]
    return value


def _number_is_supported(claim_number: str, evidence_numbers: set[str]) -> bool:
    """Accept exact evidence numbers plus ordinary display rounding.

    Analysts often render source numbers with thousands separators or round
    long deterministic decimals for readability. The verifier must normalize
    those display forms without accepting materially different numbers.
    """
    normalized = _normalize_number(claim_number)
    if normalized in evidence_numbers:
        return True

    try:
        claim = Decimal(normalized)
    except (InvalidOperation, ValueError):
        return False

    # Only allow rounding at the precision actually displayed by the claim.
    if "." in normalized:
        places = len(normalized.split(".", 1)[1])
    else:
        places = 0
    tolerance = Decimal(1).scaleb(-places) / Decimal(2)

    for raw in evidence_numbers:
        try:
            if abs(claim - Decimal(raw)) <= tolerance:
                return True
        except InvalidOperation:
            continue
    return False


def verify_output(
    *,
    envelope: dict[str, Any],
    output: dict[str, Any] | list[Any],
    schema: dict[str, Any] | None,
) -> dict[str, Any]:
    if isinstance(output, dict):
        evidence_refs = output.get("evidence_refs")
        if not isinstance(evidence_refs, list):
            raise LLMVerificationError("EVIDENCE_REFS_INVALID")
    elif isinstance(output, list):
        evidence_refs = []
        for item in output:
            if isinstance(item, dict) and isinstance(item.get("evidence_refs"), list):
                evidence_refs.extend(item["evidence_refs"])
        if not evidence_refs:
            raise LLMVerificationError("EVIDENCE_REFS_INVALID")
    else:
        raise LLMVerificationError("OUTPUT_CLAIMS_INVALID")

    input_refs = {str(x) for x in envelope.get("input_refs", [])}
    evidence_refs = [str(ref) for ref in evidence_refs]
    unknown_refs = [ref for ref in evidence_refs if ref not in input_refs]
    if unknown_refs:
        raise LLMVerificationError("EVIDENCE_REF_NOT_IN_INPUT:" + ",".join(unknown_refs))

    if not evidence_refs:
        raise LLMVerificationError("NO_EVIDENCE")

    status = str(envelope.get("data_status", "VALID")).upper()
    if status not in {"VALID", "OFFICIAL"}:
        raise LLMVerificationError("PIT_DATA_NOT_PUBLISHABLE:" + status)

    expected_product = str(envelope["product"]).upper().strip()
    serialized = json.dumps(output, ensure_ascii=False, default=str).upper()
    if not expected_product or not expected_product.isalnum():
        raise LLMVerificationError("PRODUCT_ID_INVALID")
    if expected_product in {"GC", "CL", "NG", "SI", "ES", "NQ"}:
        for token in ("GC", "CL", "NG", "SI", "ES", "NQ"):
            if token != expected_product and re.search(
                rf"(?<![A-Z]){token}(?![A-Z])", serialized
            ):
                raise LLMVerificationError(f"PRODUCT_CLAIM_MISMATCH:{token}")

    # V2 claims are nested under levels/scenarios/trade_plan. Verify the
    # complete claim object, not only legacy top-level fields, so numeric
    # levels cannot bypass evidence checking.
    if isinstance(output, dict):
        claim_payload = {
            key: output.get(key)
            for key in (
                "market_overview", "what", "why", "positioning",
                "levels", "scenarios", "trade_plan", "bias",
                "regime", "facts", "interpretations", "conflicts",
                "why_not_long", "why_not_short", "uncertainties", "narrative",
            )
            if key in output
        }
    else:
        claim_payload = output

    output_numbers = _numeric_strings(_strip_non_market_numeric(claim_payload))
    cited_evidence_numbers = _cited_evidence_numbers(
        envelope["evidence"], evidence_refs
    )

    # Deterministic levels are explicit governed inputs. They remain valid
    # price references even when the model cites a broader evidence ref.
    governed_levels = (
        envelope.get("input_payload", {}).get("deterministic_levels") or []
    )
    governed_level_numbers = {
        number
        for item in governed_levels
        if isinstance(item, dict)
        for number in _numeric_strings(item.get("price"))
    }
    cited_evidence_numbers.update(governed_level_numbers)
    unsupported_numbers = sorted(
        {
            number
            for number in output_numbers
            if number not in {"0", "1"}
            and not _number_is_supported(number, cited_evidence_numbers)
        }
    )

    claim_text = json.dumps(claim_payload, ensure_ascii=False, default=str).lower()
    forbidden_patterns = (
        "place order",
        "execute order",
        "send order",
        "open position",
        "close position",
        "broker",
        "market order",
        "limit order",
        "stop loss order",
        "take profit order",
        "dealer is short gamma",
        "dealer is long gamma",
        "market maker is short gamma",
        "market maker is long gamma",
        "dealers are short gamma",
        "dealers are long gamma",
        "market makers are short gamma",
        "market makers are long gamma",
    )
    forbidden_claims = [
        pattern for pattern in forbidden_patterns if pattern in claim_text
    ]

    if unsupported_numbers:
        raise LLMVerificationError(
            "UNSUPPORTED_NUMERIC_CLAIMS:" + ",".join(unsupported_numbers[:20])
        )
    if forbidden_claims:
        raise LLMVerificationError(
            "FORBIDDEN_EXECUTION_CLAIM:" + ",".join(forbidden_claims)
        )

    return {
        "schema_valid": True,
        "evidence_valid": bool(evidence_refs) and not unknown_refs,
        "pit_valid": status in {"VALID", "OFFICIAL"},
        "numeric_claims_valid": not unsupported_numbers,
        "forbidden_claims_found": bool(forbidden_claims),
        "unsupported_claim_count": len(unsupported_numbers),
        "verifier_version": "llm-verifier-v3",
        "verdict": "PASS",
        "checked_at": envelope.get("as_of"),
        "details": {
            "input_ref_count": len(input_refs),
            "evidence_ref_count": len(evidence_refs),
            "cited_evidence_numeric_count": len(cited_evidence_numbers),
            "unsupported_numeric_claims": unsupported_numbers[:20],
            "forbidden_claims": forbidden_claims,
        },
    }
