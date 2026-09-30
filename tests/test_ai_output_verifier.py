from intelligence.analysis.verifier import verify_output


def test_verifier_rejects_unsupported_numbers_and_forbidden_language():
    result = verify_output(
        "Buy now at 123.45, guaranteed profit",
        allowed_numbers={100.0},
        source_urls=set(),
        required_metadata={
            "as_of": "2026-10-01T00:00:00+00:00",
            "data_age": 1,
            "data_quality": 1,
            "dataset_version": "v1",
            "calculation_version": "c1",
            "assumptions": ("x",),
        },
    )
    assert result.ok is False
    assert any(v.startswith("UNSUPPORTED_NUMBER") for v in result.violations)
    assert any(v.startswith("FORBIDDEN_LANGUAGE") for v in result.violations)


def test_structured_verifier_rejects_unknown_scenario_level():
    from types import SimpleNamespace
    from datetime import datetime, timezone
    from intelligence.analysis.verifier import verify_scenario_plan

    state = SimpleNamespace(
        as_of=datetime(2026, 10, 1, tzinfo=timezone.utc),
        data_age_seconds=0,
        data_quality=1.0,
        dataset_version="v1",
        calculation_version="c1",
        assumptions=("x",),
        price=100.0,
        gamma_flip=99.0,
        call_wall=105.0,
        put_wall=95.0,
    )
    plan = SimpleNamespace(
        key_levels=(123.0,),
        trigger=("price accepts above:123.0",),
        confirmation=("market_state_remains_valid",),
        invalidation=("price rejects below:95.0",),
        risk_factors=("scenario_is_conditional",),
    )
    result = verify_scenario_plan(plan, market_state=state)
    assert result.ok is False
    assert any(v.startswith("UNSUPPORTED_LEVEL") for v in result.violations)
