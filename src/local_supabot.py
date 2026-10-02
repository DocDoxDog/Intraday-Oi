"""Self-contained supaBOT execution core for Intraday-Oi.

The repository owns the complete governed LLM path:
task router -> canonical schema -> Gemini -> semantic verifier -> telemetry.

There is no dependency on checking out or authenticating to another repository.
"""

from __future__ import annotations

from typing import Any

try:
    from .llm_gateway import LLMGateway, LLMGatewayError, _schema_for_task
    from .llm_verifier import LLMVerificationError, verify_output
    from .llm_telemetry import persist_llm_run, persist_llm_verification
except ImportError:
    # python src/main.py executes src as the import root.
    from llm_gateway import LLMGateway, LLMGatewayError, _schema_for_task
    from llm_verifier import LLMVerificationError, verify_output
    from llm_telemetry import persist_llm_run, persist_llm_verification


class LocalSupaBOTError(RuntimeError):
    pass


def generate_market_narrative(
    envelope: dict[str, Any],
    *,
    static_prefix: str,
    dynamic: dict[str, Any],
) -> dict[str, Any]:
    """Run the governed supaBOT-compatible market narrative pipeline."""

    gateway = LLMGateway()
    try:
        result = gateway.generate(
            envelope,
            static_prefix=static_prefix,
            dynamic_suffix=dynamic,
        )
    except LLMGatewayError as exc:
        raise LocalSupaBOTError(str(exc)) from exc

    claims = result.get("claims")
    if not isinstance(claims, (dict, list)):
        raise LocalSupaBOTError("GATEWAY_CLAIMS_INVALID")

    schema = _schema_for_task(envelope["task"])
    try:
        verification = verify_output(
            envelope=envelope,
            output=claims,
            schema=schema,
        )
    except LLMVerificationError as exc:
        # One governed repair pass: keep verification strict, but let the same
        # LLM correct unsupported numeric claims instead of immediately falling
        # back to DEGRADED. The repair sees the exact evidence again.
        repair_prompt = (
            static_prefix.strip()
            + "\n\nCORRECTION PASS — the previous JSON was rejected by the verifier."
            + f"\nVerifier error: {exc}"
            + "\nRewrite the full JSON contract."
            + "\nRemove or replace every unsupported numeric price with an exact value from "
              "input_payload.deterministic_levels/current/history/news evidence."
            + "\nDo not calculate new prices. Do not round into new values; the renderer handles display formatting."
            + "\nKeep all analysis sections and make trade_plan CONDITIONAL when a trigger has not occurred."
            + "\nPrevious JSON:\n"
            + __import__("json").dumps(claims, ensure_ascii=False, default=str)
        )
        try:
            repaired = gateway.generate(
                envelope,
                static_prefix=repair_prompt,
                dynamic_suffix=dynamic,
            )
            claims = repaired.get("claims")
            if not isinstance(claims, (dict, list)):
                raise LocalSupaBOTError("GATEWAY_CLAIMS_INVALID_AFTER_REPAIR")
            result = repaired
            verification = verify_output(
                envelope=envelope,
                output=claims,
                schema=schema,
            )
        except LLMVerificationError as repair_exc:
            result["status"] = "VERIFICATION_FAILED"
            result["error_code"] = f"{exc};REPAIR:{repair_exc}"
            _persist_non_blocking(result, envelope, None)
            raise LocalSupaBOTError(
                f"LLM_VERIFICATION_FAILED:{repair_exc}"
            ) from repair_exc
        except Exception as repair_exc:
            result["status"] = "VERIFICATION_FAILED"
            result["error_code"] = f"{exc};REPAIR:{repair_exc}"
            _persist_non_blocking(result, envelope, None)
            raise LocalSupaBOTError(
                f"LLM_VERIFICATION_FAILED:{repair_exc}"
            ) from repair_exc

    result["verification"] = verification
    _persist_non_blocking(result, envelope, verification)
    return result


def _persist_non_blocking(
    result: dict[str, Any],
    envelope: dict[str, Any],
    verification: dict[str, Any] | None,
) -> None:
    """Telemetry must never make market analysis unavailable."""

    try:
        persist_llm_run(result, envelope)
        if verification is not None:
            persist_llm_verification(result["run_id"], verification)
        result["telemetry_status"] = "PERSISTED"
    except Exception as exc:
        result["telemetry_status"] = "UNAVAILABLE"
        result["telemetry_error"] = str(exc)[:300]
