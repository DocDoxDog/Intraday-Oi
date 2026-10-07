from __future__ import annotations

from src import local_supabot


def test_numeric_verifier_repair_forbids_derived_numbers(monkeypatch):
    calls = []

    class FakeGateway:
        def generate(self, envelope, *, static_prefix, dynamic_suffix):
            calls.append(static_prefix)
            if len(calls) == 1:
                return {
                    "status": "SUCCESS",
                    "claims": {
                        "evidence_refs": ["E1"],
                        "narrative": {"summary": "risk/reward 1.5"},
                    },
                    "run_id": "r1",
                }
            return {
                "status": "SUCCESS",
                "claims": {
                    "evidence_refs": ["E1"],
                    "narrative": {"summary": "risk/reward remains conditional"},
                },
                "run_id": "r2",
            }

    monkeypatch.setattr(local_supabot, "LLMGateway", FakeGateway)
    monkeypatch.setattr(local_supabot, "_persist_non_blocking", lambda *args, **kwargs: None)

    envelope = {
        "product": "GC",
        "data_status": "VALID",
        "as_of": "2026-10-07T08:51:18+00:00",
        "input_refs": ["E1"],
        "evidence": {"E1": {"price": 4126.55326}},
        "input_payload": {
            "deterministic_levels": [{"price": 4126.55326}],
        },
    }

    result = local_supabot.generate_market_narrative(
        envelope,
        static_prefix="analyst contract",
        dynamic={"derived_numeric_policy": "deterministic engine owns derived numbers"},
    )

    assert len(calls) == 2
    assert "Unsupported values reported by verifier MUST disappear" in calls[1]
    assert "Do not calculate RR yourself" in calls[1]
    assert result["verification"]["verdict"] == "PASS"
