from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from intelligence.analysis.models import MarketAnalysis
from intelligence.analysis.verifier import VerificationResult, verify_market_analysis

class AnalysisProvider(Protocol):
    def generate(self, context: dict) -> MarketAnalysis: ...

@dataclass(frozen=True)
class VerifiedAnalysis:
    analysis: MarketAnalysis
    verification: VerificationResult

class AnalysisService:
    """AI interpretation boundary; deterministic verification is mandatory."""
    def __init__(self, provider: AnalysisProvider):
        self.provider = provider

    def generate(self, *, context: dict, market_state) -> VerifiedAnalysis:
        analysis = self.provider.generate(context)
        verification = verify_market_analysis(analysis, market_state=market_state)
        if not verification.ok:
            raise ValueError("AI_OUTPUT_VERIFICATION_FAILED:" + ",".join(verification.violations))
        return VerifiedAnalysis(analysis=analysis, verification=verification)