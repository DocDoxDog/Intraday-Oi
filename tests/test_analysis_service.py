from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from intelligence.analysis.models import MarketAnalysis
from intelligence.analysis.service import AnalysisService


STATE = SimpleNamespace(
    price=100.0, oi=1000.0, oi_change=10.0, gex=20.0, dex=5.0, iv=18.0,
    realized_vol=16.0, gamma_flip=99.0, call_wall=105.0, put_wall=95.0,
    as_of=datetime(2026, 10, 1, tzinfo=timezone.utc), data_age_seconds=2,
    data_quality=1.0, dataset_version="d1", calculation_version="c1",
    assumptions=("x",), data_status="VALID",
)

class Provider:
    def __init__(self, level):
        self.level = level
    def generate(self, context):
        return MarketAnalysis(
            market_context="context", what_changed="changed", why_it_matters="matters",
            key_levels=(self.level,), risk_factors=(), uncertainties=(), evidence=(),
            confidence=0.5, generated_at="2026-10-01T00:00:00+00:00",
            model_version="m1", dataset_version="d1", calculation_version="c1",
        )

def test_analysis_service_accepts_verified_output():
    result = AnalysisService(Provider(105.0)).generate(context={}, market_state=STATE)
    assert result.verification.ok

def test_analysis_service_blocks_unknown_level():
    with pytest.raises(ValueError, match="AI_OUTPUT_VERIFICATION_FAILED"):
        AnalysisService(Provider(123.0)).generate(context={}, market_state=STATE)