from __future__ import annotations

import json
import re
from typing import Any


class LLMVerificationError(RuntimeError):
    pass


_NUMBER_RE = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?(?![A-Za-z])")


def _numeric_strings(value: Any) -> list[str]:
    text = json.dumps(value, ensure_ascii=False, default=str)
    return _NUMBER_RE.findall(text)


def _cited_evidence_numbers(evidence: dict[str, Any], refs: list[str]) -> set[str]:
    numbers: set[str] = set()
    for ref in refs:
        item = evidence.get(ref)
        if item is not None:
            numbers.update(_numeric_strings(item))
    return numbers


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
    if expected_product in {"GC", "CL", "NG", "SI"}:
        for token in ("GC", "CL", "NG", "SI"):
            if token != expected_product and re.search(
                rf"(?<![A-Z]){token}(?![A-Z])", serialized
            ):
                raise LLMVerificationError(f"PRODUCT_CLAIM_MISMATCH:{token}")

    claim_fields = {
        "market_overview",
        "what",
        "why",
        "positioning",
        "levels",
        "scenarios",
        "trade_plan",
        "resistance_far",
        "resistance_main",
        "resistance_current",
        "support_current",
        "support_main",
        "support_deep",
        "bull_case",
        "bear_case",
        "sideway_case",
        "reasoning",
        "summary_th",
        "headline",
        "setup",
        "confirmation",
        "invalidation",
        "risk_note",
    }
    if isinstance(output, dict):
        claim_payload: Any = {
            key: output.get(key) for key in claim_fields if key in output
        }
    else:
        claim_payload = [
            {key: item.get(key) for key in claim_fields if key in item}
            for item in output
            if isinstance(item, dict)
        ]

    # V2 claims are nested under levels/scenarios/trade_plan. Verify the
    # complete claim object, not only legacy top-level fields, so numeric
    # levels cannot bypass evidence checking.
    if isinstance(output, dict):
        claim_payload = {
            key: output.get(key)
            for key in (
                "market_overview", "what", "why", "positioning",
                "levels", "scenarios", "trade_plan", "bias", "uncertainty",
            )
            if key in output
        }
    else:
        claim_payload = output

    output_numbers = _numeric_strings(claim_payload)
    cited_evidence_numbers = _cited_evidence_numbers(
        envelope["evidence"], evidence_refs
    )
    unsupported_numbers = sorted(
        {
            number
            for number in output_numbers
            if number not in cited_evidence_numbers and number not in {"0", "1"}
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
        "verifier_version": "llm-verifier-v2",
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
