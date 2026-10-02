from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import requests


class LLMRouterError(RuntimeError):
    pass


@dataclass(frozen=True)
class RouteConfig:
    key: str
    model: str
    stable: bool
    enabled: bool


@dataclass(frozen=True)
class TaskConfig:
    key: str
    route: str
    fallback: str | None
    temperature: float
    max_output_tokens: int
    output_schema: str | None
    output_schema_version: str | None
    enabled: bool


def _gemini_response_schema(schema: dict[str, Any]) -> dict[str, Any]:
        """Convert canonical JSON Schema to Gemini responseSchema dialect.

        The canonical schema remains full JSON Schema for local validation. Gemini's
        generateContent responseSchema is a narrower schema dialect and rejects
        keywords such as additionalProperties. Strip unsupported validation-only
        keywords at the provider boundary rather than weakening the canonical schema.
        """
        unsupported = {
            "additionalProperties",
            "$schema",
            "$id",
            "$ref",
            "$defs",
            "definitions",
            "title",
            "description",
            "default",
            "examples",
            "pattern",
            "format",
            "minLength",
            "maxLength",
            "minimum",
            "maximum",
            "exclusiveMinimum",
            "exclusiveMaximum",
            "minItems",
            "maxItems",
            "uniqueItems",
        }

        def clean(value: Any) -> Any:
            if isinstance(value, dict):
                return {k: clean(v) for k, v in value.items() if k not in unsupported}
            if isinstance(value, list):
                return [clean(v) for v in value]
            return value

        return clean(schema)



class GeminiRouter:
    """Canonical task router; downstream repositories never select models."""

    def __init__(
        self,
        config_path: str | Path | None = None,
        api_key: str | None = None,
        timeout_seconds: int = 45,
    ) -> None:
        path = Path(config_path or Path(__file__).resolve().parents[1] / "config" / "llm_routes.json")
        self._config = json.loads(path.read_text(encoding="utf-8"))
        self._validate_config()
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.base_url = (self._config.get("api") or {}).get(
            "base_url", "https://generativelanguage.googleapis.com/v1beta"
        ).rstrip("/")

    def _validate_config(self) -> None:
        models = self._config.get("models") or {}
        tasks = self._config.get("tasks") or {}
        for task_key, raw in tasks.items():
            route_key = str(raw.get("route", ""))
            if route_key not in models:
                raise LLMRouterError(
                    f"INVALID_LLM_ROUTE_CONFIG:{task_key}:route:{route_key}"
                )
            fallback = raw.get("fallback")
            if fallback is not None and str(fallback) not in models:
                raise LLMRouterError(
                    f"INVALID_LLM_ROUTE_CONFIG:{task_key}:fallback:{fallback}"
                )
            if fallback is not None and str(fallback) == route_key:
                raise LLMRouterError(f"INVALID_LLM_FALLBACK:{task_key}")

    def _route(self, key: str) -> RouteConfig:
        try:
            raw = self._config["models"][key]
            route = RouteConfig(key=key, model=str(raw["model"]), stable=bool(raw.get("stable", True)), enabled=bool(raw.get("enabled", True)))
            if not route.enabled:
                raise LLMRouterError(f"DISABLED_LLM_ROUTE:{key}")
            return route
        except KeyError as exc:
            raise LLMRouterError(f"UNKNOWN_LLM_ROUTE:{key}") from exc

    def task(self, task_key: str) -> TaskConfig:
        try:
            raw = self._config["tasks"][task_key]
        except KeyError as exc:
            raise LLMRouterError(f"UNKNOWN_LLM_TASK:{task_key}") from exc
        if not bool(raw.get("enabled", True)):
            raise LLMRouterError(f"DISABLED_LLM_TASK:{task_key}")
        route_key = str(raw["route"])
        fallback = raw.get("fallback")
        if fallback is not None:
            fallback = str(fallback)
            if fallback == route_key:
                raise LLMRouterError(f"INVALID_LLM_FALLBACK:{task_key}")
        return TaskConfig(
            key=task_key,
            route=route_key,
            fallback=fallback,
            temperature=float(raw.get("temperature", 0.2)),
            max_output_tokens=int(raw.get("max_output_tokens", 2000)),
            output_schema=raw.get("output_schema"),
            output_schema_version=raw.get("output_schema_version"),
            enabled=True,
        )

    @staticmethod
    def _transient(exc: Exception) -> bool:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        return status in {408, 409, 425, 429, 500, 502, 503, 504} or isinstance(
            exc, (requests.Timeout, requests.ConnectionError)
        )

    @staticmethod
    def _text(response_json: dict[str, Any]) -> str:
        candidates = response_json.get("candidates") or []
        if not candidates:
            raise LLMRouterError("GEMINI_NO_CANDIDATE")
        parts = ((candidates[0].get("content") or {}).get("parts") or [])
        text = "".join(str(part.get("text") or "") for part in parts if isinstance(part, dict)).strip()
        if not text:
            raise LLMRouterError("GEMINI_EMPTY_TEXT")
        return text

    def _call_once(
            self,
            route: RouteConfig,
            task: TaskConfig,
            *,
            system_instruction: str,
            user_payload: dict[str, Any],
            response_schema: dict[str, Any] | None,
        ) -> dict[str, Any]:
            body: dict[str, Any] = {
                "systemInstruction": {"parts": [{"text": system_instruction}]},
                "contents": [{"role": "user", "parts": [{"text": json.dumps(user_payload, ensure_ascii=False, default=str)}]}],
                "generationConfig": {
                    "maxOutputTokens": task.max_output_tokens,
                },
            }
            # Gemini 2.5 Flash supports the standard sampling parameters.
            # Keep temperature enabled for the 2.5 Flash production route.
            if not route.model.startswith("gemini-3."):
                body["generationConfig"]["temperature"] = task.temperature
    
            if response_schema:
                # generateContent structured output uses responseMimeType + responseSchema.
                # Keep this compatible with Gemini 3.x while preserving the governed schema.
                body["generationConfig"]["responseMimeType"] = "application/json"
                body["generationConfig"]["responseSchema"] = _gemini_response_schema(response_schema)
            # Gemini 2.5 Flash uses thinkingBudget when thinking control is needed.
            # Leave it unset here so the model keeps its default dynamic thinking behavior.
    
            started_at = datetime.now(timezone.utc).isoformat()
            timer = time.perf_counter()
            try:
                response = requests.post(
                    f"{self.base_url}/models/{route.model}:generateContent",
                    headers={"x-goog-api-key": self.api_key or "", "Content-Type": "application/json"},
                    json=body,
                    timeout=self.timeout_seconds,
                )
                response.raise_for_status()
                data = response.json()
                output_text = self._text(data)
            except requests.HTTPError as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                detail = ""
                response = getattr(exc, "response", None)
                if response is not None:
                    try:
                        detail = response.text.replace("\n", " ").strip()[:600]
                    except Exception:
                        detail = ""
                suffix = f":HTTP_{status}" if status is not None else ""
                if detail:
                    suffix += f":{detail}"
                err = LLMRouterError(f"GEMINI_HTTP_ERROR{suffix}")
                # Preserve the provider response so the router can still classify
                # 408/409/425/429/5xx as transient and use the configured fallback.
                err.response = response
                raise err from exc
            except (requests.Timeout, requests.ConnectionError):
                # Keep the native exception type so transient retry logic remains intact.
                raise
            except requests.RequestException as exc:
                raise LLMRouterError(f"GEMINI_REQUEST_ERROR:{type(exc).__name__}:{exc}") from exc
            except Exception as exc:
                raise LLMRouterError(f"GEMINI_RESPONSE_ERROR:{type(exc).__name__}:{exc}") from exc
            completed_at = datetime.now(timezone.utc).isoformat()
            usage = data.get("usageMetadata") or {}
            return {
                "run_id": str(uuid.uuid4()),
                "status": "OK",
                "route": route.key,
                "model": route.model,
                "model_version": data.get("modelVersion"),
                "response_id": data.get("responseId"),
                "started_at": started_at,
                "completed_at": completed_at,
                "latency_ms": int((time.perf_counter() - timer) * 1000),
                "input_tokens": usage.get("promptTokenCount"),
                "output_tokens": usage.get("candidatesTokenCount"),
                "cached_tokens": usage.get("cachedContentTokenCount"),
                "text": output_text,
            }
    
    def generate(
        self,
        task_key: str,
        *,
        system_instruction: str,
        user_payload: dict[str, Any],
        response_schema: dict[str, Any] | None = None,
        validator: Callable[[dict[str, Any]], None] | None = None,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        task = self.task(task_key)
        key = api_key or self.api_key
        if not key:
            raise LLMRouterError("GEMINI_API_KEY_MISSING")
        self.api_key = key
        if response_schema is None and task.output_schema:
            schema_path = Path(__file__).resolve().parents[1] / task.output_schema
            response_schema = json.loads(schema_path.read_text(encoding="utf-8"))

        routes = [task.route] + ([task.fallback] if task.fallback else [])
        last_error: Exception | None = None
        for index, route_key in enumerate(routes):
            route = self._route(route_key)
            try:
                result = self._call_once(
                    route, task,
                    system_instruction=system_instruction,
                    user_payload=user_payload,
                    response_schema=response_schema,
                )
                if validator:
                    parsed = json.loads(result["text"]) if response_schema else {"text": result["text"]}
                    validator(parsed)
                result["fallback_used"] = index > 0
                result["requested_task"] = task_key
                result["requested_route"] = task.route
                return result
            except Exception as exc:
                last_error = exc
                if index == 0 and task.fallback and self._transient(exc):
                    continue
                break
        raise LLMRouterError(f"LLM_TASK_FAILED:{task_key}:{last_error}") from last_error
