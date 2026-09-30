from __future__ import annotations

import os
from typing import Any

from supabase import Client, create_client

from intelligence.news.models import MarketConfirmation, NewsImpact, NewsItem, StoryCluster
from intelligence.scenario.models import ScenarioPlan


class SupabaseIntelligenceWriter:
    """Server-side writer for metadata-safe intelligence objects."""

    def __init__(self, *, client: Client | None = None, url: str | None = None, service_role_key: str | None = None):
        if client is not None:
            self.client = client
            return
        db_url = url or os.environ.get("SUPABASE_URL")
        key = service_role_key or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        if not db_url or not key:
            raise RuntimeError("SUPABASE_SERVER_CREDENTIALS_MISSING")
        self.client = create_client(db_url, key)

    def put_news(self, item: NewsItem) -> None:
        row = {
            "news_id": item.news_id,
            "headline": item.headline,
            "source": item.source,
            "url": item.url,
            "published_at": item.published_at.isoformat(),
            "detected_at": item.detected_at.isoformat(),
            "event_time": item.event_time.isoformat() if item.event_time else None,
            "language": item.language,
            "category": item.category,
            "entities": list(item.entities),
            "assets": list(item.assets),
            "severity": item.severity.value,
            "status": item.status.value,
            "provenance_id": item.provenance_id,
        }
        self.client.table("oi_core_news_items").upsert(row, on_conflict="news_id").execute()

    def put_story_cluster(self, cluster: StoryCluster) -> None:
        row = {
            "cluster_id": cluster.cluster_id,
            "canonical_headline": cluster.canonical_headline,
            "news_ids": list(cluster.news_ids),
            "source_count": cluster.source_count,
            "first_published_at": cluster.first_published_at.isoformat(),
            "last_published_at": cluster.last_published_at.isoformat(),
            "official_source": cluster.official_source,
        }
        self.client.table("oi_core_story_clusters").upsert(row, on_conflict="cluster_id").execute()

    def put_confirmation(self, cluster_id: str, confirmation: MarketConfirmation) -> None:
        row = {
            "cluster_id": cluster_id,
            "confirmed": confirmation.confirmed,
            "score": confirmation.score,
            "price_reaction": confirmation.price_reaction,
            "volatility_reaction": confirmation.volatility_reaction,
            "oi_change": confirmation.oi_change,
            "gex_change": confirmation.gex_change,
            "dex_change": confirmation.dex_change,
            "market_state_changed": confirmation.market_state_changed,
            "evidence": list(confirmation.evidence),
        }
        self.client.table("oi_core_market_confirmations").insert(row).execute()

    def put_impact(self, impact: NewsImpact, confirmation_id: int | None = None) -> None:
        row = {
            "news_id": impact.news_id,
            "cluster_id": impact.story_cluster_id,
            "severity": impact.severity.value,
            "confidence": impact.confidence,
            "assets": list(impact.assets),
            "direction": impact.direction.value,
            "horizon": impact.horizon,
            "impact_reason": list(impact.impact_reason),
            "source_count": impact.source_count,
            "official_source": impact.official_source,
            "market_confirmation_id": confirmation_id,
            "model_version": impact.model_version,
        }
        self.client.table("oi_core_news_impacts").upsert(
            row, on_conflict="news_id,cluster_id"
        ).execute()

    def put_analysis(
        self,
        *,
        symbol: str,
        as_of: str,
        market_context: str,
        what_changed: str,
        why_it_matters: str,
        key_levels: list[Any],
        risk_factors: list[str],
        uncertainties: list[str],
        evidence: list[str],
        confidence: float,
        model_version: str,
        dataset_version: str,
        calculation_version: str,
    ) -> None:
        self.client.table("oi_core_market_analyses").insert({
            "symbol": symbol,
            "as_of": as_of,
            "market_context": market_context,
            "what_changed": what_changed,
            "why_it_matters": why_it_matters,
            "key_levels": key_levels,
            "risk_factors": risk_factors,
            "uncertainties": uncertainties,
            "evidence": evidence,
            "confidence": confidence,
            "model_version": model_version,
            "dataset_version": dataset_version,
            "calculation_version": calculation_version,
        }).execute()

    def put_scenario(self, scenario: ScenarioPlan) -> None:
        self.client.table("oi_core_scenario_plans").upsert({
            "scenario_id": scenario.scenario_id,
            "market": scenario.market,
            "directional_bias": scenario.directional_bias,
            "trigger": list(scenario.trigger),
            "confirmation": list(scenario.confirmation),
            "invalidation": list(scenario.invalidation),
            "key_levels": list(scenario.key_levels),
            "risk_factors": list(scenario.risk_factors),
            "supporting_evidence": list(scenario.supporting_evidence),
            "contradicting_evidence": list(scenario.contradicting_evidence),
            "confidence": scenario.confidence,
            "valid_until": scenario.valid_until.isoformat(),
            "version": scenario.version,
            "status": scenario.status,
        }, on_conflict="scenario_id").execute()
