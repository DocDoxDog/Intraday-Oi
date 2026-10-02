from src.llm_router import GeminiRouter, RouteConfig, TaskConfig


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200
        self.text = ""

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _task():
    return TaskConfig(
        key="market.narrative",
        route="standard",
        fallback="fast",
        temperature=0.2,
        max_output_tokens=2200,
        output_schema="schemas/llm/market_analyst_v2.json",
        output_schema_version="market-analyst.v2",
        enabled=True,
    )


def test_gemini_25_flash_disables_dynamic_thinking_for_structured_output(monkeypatch):
    calls = []

    def fake_post(*args, **kwargs):
        calls.append(kwargs["json"])
        return _FakeResponse({
            "modelVersion": "gemini-2.5-flash",
            "responseId": "test-response",
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": '{"ok":true}',
                    }]
                }
            }]
        })

    monkeypatch.setattr("src.llm_router.requests.post", fake_post)

    router = GeminiRouter(api_key="test-key")
    route = RouteConfig(
        key="standard",
        model="gemini-2.5-flash",
        stable=True,
        enabled=True,
    )

    result = router._call_once(
        route,
        _task(),
        system_instruction="test",
        user_payload={"x": 1},
        response_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
    )

    config = calls[0]["generationConfig"]
    assert config["thinkingConfig"] == {"thinkingBudget": 0}
    assert config["responseMimeType"] == "application/json"
    assert result["text"] == '{"ok":true}'


def test_gemini_text_ignores_thought_parts():
    payload = {
        "candidates": [{
            "content": {
                "parts": [
                    {"text": "internal reasoning", "thought": True},
                    {"text": '{"ok":true}'},
                ]
            }
        }]
    }
    assert GeminiRouter._text(payload) == '{"ok":true}'
