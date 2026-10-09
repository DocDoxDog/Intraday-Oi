from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .llm_router import GeminiRouter


class LLMGatewayError(RuntimeError):
    pass


ROOT = Path(__file__).resolve().parents[1]
ROUTE_CONFIG_PATH = ROOT / "config" / "llm_routes.json"


def _load_route_config() -> dict[str, Any]:
    return json.loads(ROUTE_CONFIG_PATH.read_text(encoding="utf-8"))


def _normalize_schema(schema: dict[str, Any]) -> dict[str, Any]:
    out = json.loads(json.dumps(schema))
    mapping = {"OBJECT":"object","ARRAY":"array","STRING":"string","INTEGER":"integer","NUMBER":"number","BOOLEAN":"boolean"}
    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if isinstance(value.get("type"), str):
                value["type"] = mapping.get(value["type"], value["type"])
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(out)
    return out


def _schemas_equal(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return _normalize_schema(left) == _normalize_schema(right)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value: Any, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise LLMGatewayError(f"INVALID_TIMESTAMP:{field}") from exc
    if parsed.tzinfo is None:
        raise LLMGatewayError(f"TIMESTAMP_TIMEZONE_REQUIRED:{field}")
    return parsed.astimezone(timezone.utc)


def _task_config(task: str) -> dict[str, Any]:
    config = _load_route_config()
    tasks = config.get("tasks") or {}
    if task not in tasks:
        raise LLMGatewayError(f"UNKNOWN_LLM_TASK:{task}")
    return tasks[task]


def _schema_for_task(task: str) -> dict[str, Any] | None:
    raw = _task_config(task)
    schema_path = raw.get("output_schema")
    if not schema_path:
        return None
    return json.loads((ROOT / schema_path).read_text(encoding="utf-8"))


def _schema_version_for_task(task: str) -> str | None:
    return _task_config(task).get("output_schema_version")


def _skill_for_task(task: str) -> str | None:
    path = _task_config(task).get("skill_file")
    if not path:
        return None
    skill_path = ROOT / path
    if not skill_path.is_file():
        raise LLMGatewayError(f"SKILL_FILE_NOT_FOUND:{task}:{path}")
    return skill_path.read_text(encoding="utf-8").strip()


def _validate_pit(envelope: dict[str, Any]) -> None:
    now = _utc_now()
    as_of = _parse_ts(envelope["as_of"], "as_of")
    if as_of > now:
        raise LLMGatewayError("FUTURE_AS_OF")
    for ref, item in envelope["evidence"].items():
        if not isinstance(item, dict):
            continue
        times: dict[str, datetime] = {}
        for key in ("publication_time","availability_time","ingestion_time","published_at","observed_at"):
            if item.get(key) is None:
                continue
            times[key] = _parse_ts(item[key], f"evidence.{ref}.{key}")
            if times[key] > now:
                raise LLMGatewayError(f"FUTURE_EVIDENCE_TIME:{ref}:{key}")
            if times[key] > as_of:
                raise LLMGatewayError(f"EVIDENCE_AFTER_AS_OF:{ref}:{key}")
        publication = times.get("publication_time") or times.get("published_at")
        availability = times.get("availability_time")
        ingestion = times.get("ingestion_time") or times.get("observed_at")
        if publication and availability and publication > availability:
            raise LLMGatewayError(f"INVALID_PIT_ORDER:{ref}:publication>availability")
        if availability and ingestion and availability > ingestion:
            raise LLMGatewayError(f"INVALID_PIT_ORDER:{ref}:availability>ingestion")


def validate_request(envelope: dict[str, Any]) -> None:
    required = ("request_id","run_id","task","repo","product","as_of","data_status","dataset_version",
                "calculation_version","prompt_version","input_refs","input_payload","evidence",
                "model_policy","output_schema_version")
    missing = [key for key in required if key not in envelope]
    if missing:
        raise LLMGatewayError("REQUEST_ENVELOPE_MISSING:" + ",".join(missing))
    for key in ("request_id","run_id","task","repo","product","dataset_version","calculation_version","prompt_version"):
        if not str(envelope[key]).strip():
            raise LLMGatewayError(f"{key.upper()}_REQUIRED")
    if not isinstance(envelope["input_refs"], list) or not envelope["input_refs"]:
        raise LLMGatewayError("INPUT_REFS_REQUIRED")
    if not isinstance(envelope["input_payload"], dict):
        raise LLMGatewayError("INPUT_PAYLOAD_INVALID")
    if not isinstance(envelope["evidence"], dict) or not envelope["evidence"]:
        raise LLMGatewayError("NO_EVIDENCE")
    data_status = str(envelope["data_status"]).upper()
    if data_status not in {"VALID","OFFICIAL"}:
        raise LLMGatewayError("REJECTED_DATA_STATUS:" + data_status)
    _validate_pit(envelope)


def build_system_instruction(static_prefix: str, *, task: str | None = None) -> str:
    suffix = (
        "\n\nNEVER invent market numbers.\n"
        "Every factual claim must be traceable to an evidence reference.\n"
        "Use only exact identifiers from input_refs in evidence_refs.\n"
        "When one evidence field is missing, mark that field UNKNOWN and continue using the valid evidence that remains.\n"
        "Never abandon the full scenario analysis solely because one field lacks a baseline.\n"
        "LLM output is interpretation only; deterministic market truth remains authoritative."
    )
    skill = _skill_for_task(task) if task else None
    if skill:
        return static_prefix.strip() + "\n\n--- DOMAIN SKILL ---\n" + skill + suffix
    return static_prefix.strip() + suffix


def build_user_payload(envelope: dict[str, Any], dynamic_suffix: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": envelope["request_id"], "run_id": envelope["run_id"], "task": envelope["task"],
        "repo": envelope["repo"], "product": envelope["product"], "as_of": envelope["as_of"],
        "dataset_version": envelope["dataset_version"], "calculation_version": envelope["calculation_version"],
        "prompt_version": envelope["prompt_version"], "input_refs": envelope["input_refs"],
        "input_payload": envelope["input_payload"], "evidence": envelope["evidence"], "dynamic": dynamic_suffix,
    }


class LLMGateway:
    def __init__(self, *, router: GeminiRouter | None = None):
        self.router = router or GeminiRouter(api_key=os.environ.get("GEMINI_API_KEY"))

    def generate(self, envelope: dict[str, Any], *, static_prefix: str,
                 dynamic_suffix: dict[str, Any], response_schema: dict[str, Any] | None = None) -> dict[str, Any]:
        validate_request(envelope)
        task = envelope["task"]
        task_config = self.router.task(task)
        canonical_schema = _schema_for_task(task)
        if canonical_schema is not None:
            expected_version = _schema_version_for_task(task)
            requested_version = str(envelope["output_schema_version"])
            if not expected_version:
                raise LLMGatewayError(f"CANONICAL_SCHEMA_VERSION_MISSING:{task}")
            if requested_version != expected_version:
                raise LLMGatewayError(f"OUTPUT_SCHEMA_VERSION_MISMATCH:{task}:{requested_version}!={expected_version}")
            if response_schema is not None and not _schemas_equal(response_schema, canonical_schema):
                raise LLMGatewayError(f"CANONICAL_SCHEMA_OVERRIDE_FORBIDDEN:{task}")
            schema = _normalize_schema(canonical_schema)
        else:
            schema = _normalize_schema(response_schema) if response_schema else None
            if schema is None:
                raise LLMGatewayError(f"OUTPUT_SCHEMA_REQUIRED:{task}")

        requested_route = task_config.route
        requested_model = self.router._route(requested_route).model
        result = self.router.generate(
            task,
            system_instruction=build_system_instruction(static_prefix, task=task),
            user_payload=build_user_payload(envelope, dynamic_suffix),
            response_schema=schema,
        )

        try:
            raw_text = str(result.get("text") or "").strip()
            if raw_text.startswith("\u0060\u0060\u0060"):
                raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text
                if raw_text.endswith("\u0060\u0060\u0060"):
                    raw_text = raw_text[:-3].rstrip()
            try:
                output = json.loads(raw_text)
            except (TypeError, ValueError):
                start = next((i for i, ch in enumerate(raw_text) if ch in "[{"), None)
                end = max(raw_text.rfind("]"), raw_text.rfind("}"))
                if start is None or end <= start:
                    raise
                output = json.loads(raw_text[start:end + 1])
        except (TypeError, ValueError) as exc:
            raise LLMGatewayError("REJECTED_JSON_OUTPUT") from exc

        try:
            Draft202012Validator(schema).validate(output)
        except Exception as exc:
            raise LLMGatewayError("REJECTED_SCHEMA_VALIDATION") from exc

        return {
            "request_id": envelope["request_id"], "run_id": envelope["run_id"], "status": "SUCCESS",
            "claims": output if isinstance(output, (dict, list)) else [],
            "uncertainties": output.get("uncertainties", []) if isinstance(output, dict) else [],
            "evidence_refs": output.get("evidence_refs", []) if isinstance(output, dict) else [],
            "model": result["model"], "actual_model": result["model"], "requested_model": requested_model,
            "model_version": result.get("model_version") or result["model"], "provider": "gemini",
            "prompt_version": envelope["prompt_version"], "schema_version": envelope["output_schema_version"],
            "data_as_of": envelope["as_of"], "started_at": result.get("started_at"),
            "completed_at": result.get("completed_at"), "created_at": result.get("completed_at") or _utc_now().isoformat(),
            "requested_route": requested_route, "fallback_used": bool(result.get("fallback_used")),
            "response_id": result.get("response_id"), "latency_ms": result.get("latency_ms"),
            "input_tokens": result.get("input_tokens"), "output_tokens": result.get("output_tokens"),
            "cached_tokens": result.get("cached_tokens"),
        }
