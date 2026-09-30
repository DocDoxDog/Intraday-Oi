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
