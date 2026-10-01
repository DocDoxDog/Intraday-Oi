from __future__ import annotations

import hashlib
import json
from typing import Any


def persist_llm_run(result: dict[str, Any], envelope: dict[str, Any]) -> None:
    from supabase_client import get_client

    payload = {
        "run_id": result["run_id"],
        "request_id": envelope["request_id"],
        "task": envelope["task"],
        "repo": envelope["repo"],
        "organization_id": envelope.get("organization_id"),
        "member_id": envelope.get("member_id"),
        "trace_id": envelope.get("trace_id"),
        "environment": envelope.get("environment"),
        "product": envelope["product"],
        "as_of": envelope["as_of"],
        "dataset_version": envelope["dataset_version"],
        "calculation_version": envelope["calculation_version"],
        "prompt_version": envelope["prompt_version"],
        "requested_route": result.get("requested_route") or "unknown",
        "requested_model": result.get("requested_model") or "unknown",
        "actual_model": result.get("actual_model") or result.get("model"),
        "model_version": result.get("model_version"),
        "provider": result.get("provider") or "unknown",
        "input_refs": envelope["input_refs"],
        "output_schema_version": envelope["output_schema_version"],
        "status": result.get("status", "INTERNAL_ERROR"),
        "started_at": result.get("started_at"),
        "completed_at": result.get("completed_at"),
        "latency_ms": result.get("latency_ms"),
        "input_tokens": result.get("input_tokens"),
        "output_tokens": result.get("output_tokens"),
        "cached_tokens": result.get("cached_tokens"),
        "response_id": result.get("response_id"),
        "output_hash": hashlib.sha256(
            json.dumps(
                result.get("claims") or {},
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ).encode("utf-8")
        ).hexdigest(),
        "fallback_used": bool(result.get("fallback_used")),
        "error_code": result.get("error_code"),
    }
    get_client().schema("llm").table("runs").insert(payload).execute()


def persist_llm_verification(
    run_id: str,
    verification: dict[str, Any],
) -> None:
    from supabase_client import get_client

    get_client().schema("llm").table("verifications").insert(
        {"run_id": run_id, **verification}
    ).execute()
