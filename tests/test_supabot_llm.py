from __future__ import annotations

from src import supabot_llm


def _fake_generate(envelope, static_prefix, dynamic):
    return {
        "status": "SUCCESS",
        "claims": {
            "market_overview": "ราคายังอยู่ใกล้ระดับอ้างอิง 4300",
            "resistance_far": "4500", "resistance_main": "4400", "resistance_current": "4350",
            "support_current": "4250", "support_main": "4200", "support_deep": "4100",
            "bull_case": "ยืนเหนือ 4350 ตาม evidence", "bear_case": "หลุด 4250 ตาม evidence",
            "sideway_case": "แกว่งในกรอบ", "bias": "WAIT", "uncertainty": 0.3,
            "evidence_refs": ["itb:oi:deterministic"], "data_limitations": []
        },
        "model": "gateway-model", "actual_model": "gateway-model", "requested_model": "gateway-model",
        "model_version": "test", "run_id": "run-1", "request_id": "req-1",
        "fallback_used": False, "latency_ms": 12, "verification": {"verdict": "PASS"}
    }


def test_builds_governed_envelope(monkeypatch):
    captured = {}
    monkeypatch.setattr(supabot_llm, "generate_market_narrative",
                        lambda envelope, static_prefix, dynamic: (captured.update(envelope=envelope) or _fake_generate(envelope, static_prefix, dynamic)))
    parsed = {
        "product_symbol":"GC","contract":"GC","future_price":4300,"cfd_price":4297,
        "observed_at":"2026-10-01T06:00:00+00:00",
        "raw_series":{"dte":1.38,"totals":{"open_interest_total":1000},
        "gex":{"net_gex":120000,"gamma_flip":4280,"call_wall":4400,"put_wall":4200},
        "strike_rows":[{"strike":4350,"oiCall":100,"oiPut":50,"net_gex":20000}]}}
    result=supabot_llm.analyze_with_supabot(parsed, history={"today":{"count":2}})
    envelope=captured["envelope"]
    assert envelope["task"]=="market.narrative"
    assert envelope["product"]=="GC"
    assert envelope["data_status"]=="VALID"
    assert envelope["output_schema_version"]=="market-narrative.v1"
    assert envelope["input_refs"]==["itb:oi:deterministic","itb:oi:history"]
    assert "deterministic_levels" in envelope["input_payload"]
    assert result["short_bias"]=="WAIT"
    assert result["llm_run_id"]=="run-1"
    assert result["llm_verification"]["verdict"]=="PASS"


def test_no_model_selection_in_adapter(monkeypatch):
    captured = {}
    monkeypatch.setattr(supabot_llm, "generate_market_narrative",
                        lambda envelope, static_prefix, dynamic: (captured.update(envelope=envelope) or _fake_generate(envelope, static_prefix, dynamic)))
    parsed={"product_symbol":"GC","contract":"GC","future_price":4300,"raw_series":{"strike_rows":[],"totals":{},"gex":{}}}
    supabot_llm.analyze_with_supabot(parsed)
    envelope=captured["envelope"]
    assert envelope["model_policy"]["selection"]=="local_supaBOT_task_router"
    assert "model" not in envelope



def test_gemini_38_flash_omits_legacy_temperature_config(monkeypatch):
    from src.llm_router import GeminiRouter

    router = GeminiRouter(api_key="test")
    captured = {}

    class Response:
        def raise_for_status(self):
            return None
        def json(self):
            return {
                "candidates": [{"content": {"parts": [{"text": "{}"}]}}],
                "modelVersion": "gemini-2.5-flash-001",
            }

    monkeypatch.setattr(
        "src.llm_router.requests.post",
        lambda url, **kwargs: (captured.update(url=url, body=kwargs["json"]) or Response()),
    )
    router._call_once(
        router._route("standard"),
        router.task("market.narrative"),
        system_instruction="test",
        user_payload={"ok": True},
        response_schema=None,
    )
    generation = captured["body"]["generationConfig"]
    assert "temperature" not in generation
    assert captured["url"].endswith("/models/gemini-3.8-flash:generateContent")


def test_gemini_schema_strips_jsonschema_only_keywords():
    from src.llm_router import _gemini_response_schema

    canonical = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "bias": {
                "type": "string",
                "enum": ["BUY", "SELL", "WAIT"],
                "description": "human-readable bias",
                "minimum": 0,
            },
            "items": {
                "type": "array",
                "items": {"type": "string", "maxLength": 20},
            },
        },
        "required": ["bias"],
    }

    provider = _gemini_response_schema(canonical)

    assert provider["type"] == "object"
    assert "additionalProperties" not in provider
    assert "description" not in provider["properties"]["bias"]
    assert "minimum" not in provider["properties"]["bias"]
    assert "maxLength" not in provider["properties"]["items"]["items"]
    assert provider["properties"]["bias"]["enum"] == ["BUY", "SELL", "WAIT"]
