"""V5.2 deterministic evidence fusion: feature -> evidence -> relationship -> conflict -> scenario."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import ceil
from statistics import quantiles
from typing import Any, Iterable

VERSION = "evidence-fusion-v5.2"


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _upper(v: Any) -> str:
    return str(v or "").strip().upper()


def _first(d: dict[str, Any] | None, *keys: str) -> float | None:
    d = d or {}
    for key in keys:
        value = _num(d.get(key))
        if value is not None:
            return value
    return None


def _dir(v: Any) -> str:
    value = _upper(v)
    if value in {"BULLISH", "LONG", "UP", "POSITIVE"}:
        return "BULLISH"
    if value in {"BEARISH", "SHORT", "DOWN", "NEGATIVE"}:
        return "BEARISH"
    return "UNKNOWN"


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    family: str
    label: str
    value: Any
    interpretation: str
    polarity: str = "NEUTRAL_CONTEXT"
    availability: str = "OBSERVED"
    provenance: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["provenance"] = list(self.provenance)
        return data


@dataclass(frozen=True)
class Relationship:
    relationship_id: str
    relation_type: str
    evidence_refs: tuple[str, ...]
    interpretation: str
    priority: str = "MEDIUM"
    direction: str = "NEUTRAL"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence_refs"] = list(self.evidence_refs)
        return data


@dataclass(frozen=True)
class Conflict:
    conflict_id: str
    severity: str
    evidence_refs: tuple[str, ...]
    interpretation: str
    resolution_hint: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence_refs"] = list(self.evidence_refs)
        return data


@dataclass
class EvidenceLedger:
    items: list[Evidence] = field(default_factory=list)

    def add(self, item: Evidence | None) -> None:
        if item is not None:
            self.items.append(item)

    def add_many(self, items: Iterable[Evidence | None]) -> None:
        for item in items:
            self.add(item)

    def get(self, key: str) -> Evidence | None:
        return next((x for x in self.items if x.evidence_id == key), None)


class EvidenceFusionEngine:
    def __init__(self, state: dict[str, Any]) -> None:
        self.state = state or {}
        self.raw = self.state.get("raw_series") or {}
        self.market = self.raw.get("market_state") or {}
        self.ledger = EvidenceLedger()
        self.relationships: list[Relationship] = []
        self.conflicts: list[Conflict] = []

    def build(self) -> dict[str, Any]:
        self._collect()
        self._relationships()
        self._conflicts()
        direction = self._structural_direction()
        return {
            "version": VERSION,
            "status": "READY" if len(self.ledger.items) >= 2 else "DATA_INSUFFICIENT",
            "design": {
                "principle": "feature->evidence->relationship->conflict->scenario",
                "directional_score": False,
                "llm_role": "narrative_only",
                "execution_authority": "NONE",
            },
            "market_context": {
                "structural_direction": direction,
                "location": self._location(),
                "regime": self.market.get("regime") or {},
            },
            "evidence": [x.to_dict() for x in self.ledger.items],
            "relationships": [x.to_dict() for x in self.relationships],
            "conflicts": [x.to_dict() for x in self.conflicts],
            "scenarios": self._scenarios(direction),
            "coverage": self._coverage(),
            "limitations": [
                "Feature families are not additive votes.",
                "OI changes do not identify aggressor direction.",
                "Block/absorption labels require event-study validation.",
                "Auction/TPO may be a bar proxy rather than true tick-by-tick TPO.",
                "3-sigma boundaries inherit the assumptions of the supplied volatility estimator.",
            ],
        }

    def _collect(self) -> None:
        price = self.market.get("price") or {}
        levels = self.market.get("levels") or {}
        technical = self.market.get("technical") or {}
        auction = self.market.get("auction") or {}
        flow = self.market.get("flow") or {}
        gamma = self.market.get("gamma") or {}
        vol = self.market.get("volatility") or {}
        quant = self.market.get("quant_metrics") or self.raw.get("quant_metrics") or {}
        order_flow = self.market.get("order_flow") or {}

        current = _first(price, "cfd", "futures")
        if current is not None:
            self.ledger.add(Evidence("price.current", "PRICE_STRUCTURE", "Current price", current,
                "Reference price for location and scenarios.", provenance=("market_state.price",)))

        direction = self._structural_direction()
        if direction != "UNKNOWN":
            self.ledger.add(Evidence("structure.direction", "PRICE_STRUCTURE", "Structural direction",
                direction, "Higher-timeframe directional context; not execution timing.",
                polarity=direction, provenance=("market_state.technical", "market_state.decision")))

        for key, label, value, meaning in (
            ("levels.support", "Support", _first(levels, "support_current", "support"),
             "Deterministic lower structure."),
            ("levels.resistance", "Resistance", _first(levels, "resistance_current", "resistance"),
             "Deterministic upper structure."),
            ("levels.gamma_flip", "Gamma flip", _first(gamma, "gamma_flip"),
             "Dealer-gamma regime boundary."),
            ("levels.call_wall", "Call wall", _first(gamma, "call_wall"),
             "Call-side gamma concentration reference."),
            ("levels.put_wall", "Put wall", _first(gamma, "put_wall"),
             "Put-side gamma concentration reference."),
        ):
            if value is not None:
                self.ledger.add(Evidence(key, "PRICE_STRUCTURE", label, value, meaning,
                    provenance=("market_state.levels",)))

        oi = {
            "put": _first(flow, "oi_put", "open_interest_view_put"),
            "call": _first(flow, "oi_call", "open_interest_view_call"),
            "delta_put": _first(flow, "oi_delta_put", "oi_change_put"),
            "delta_call": _first(flow, "oi_delta_call", "oi_change_call"),
        }
        if any(v is not None for v in oi.values()):
            self.ledger.add(Evidence("options.oi", "OPTIONS_POSITIONING", "Open interest", oi,
                "Positioning/activity context; not aggressor direction.",
                provenance=("market_state.flow",)))

        gex = _first(gamma, "net_gex")
        if gex is not None:
            self.ledger.add(Evidence("options.gamma", "OPTIONS_POSITIONING", "Net GEX", {
                "net_gex": gex,
                "gamma_flip": _first(gamma, "gamma_flip"),
                "call_wall": _first(gamma, "call_wall"),
                "put_wall": _first(gamma, "put_wall"),
            }, "Dealer gamma context, not a directional oracle.",
            polarity="POSITIVE_CONTEXT" if gex > 0 else "NEGATIVE_CONTEXT" if gex < 0 else "NEUTRAL_CONTEXT",
            provenance=("market_state.gamma",)))

        iv = _first(vol, "iv")
        skew = _first(vol, "skew")
        term = vol.get("iv_term_structure") or []
        smile = vol.get("smile") or self.raw.get("vol_surface") or self.raw.get("volatility_surface")
        if iv is not None:
            self.ledger.add(Evidence("vol.iv", "VOLATILITY", "Implied volatility", iv,
                "Current implied-volatility level.", provenance=("market_state.volatility",)))
        if skew is not None:
            self.ledger.add(Evidence("vol.skew", "VOLATILITY", "Volatility skew", skew,
                "Asymmetric option premium context; not a directional vote.",
                polarity="TAIL_PREMIUM" if skew > 0 else "CALL_PREMIUM" if skew < 0 else "BALANCED",
                provenance=("market_state.volatility.skew",)))
        if term:
            self.ledger.add(Evidence("vol.term_structure", "VOLATILITY", "IV term structure", term,
                "Volatility priced across expiries.",
                provenance=("market_state.volatility.iv_term_structure",)))
        if smile:
            self.ledger.add(Evidence("vol.smile", "VOLATILITY", "Volatility smile/surface", smile,
                "Per-strike/expiry surface evidence; future adapters may add SVI/SSVI diagnostics.",
                provenance=("market_state.volatility.smile", "raw_series.vol_surface")))

        expected = (quant.get("volatility") or {}).get("expected_range") if isinstance(quant, dict) else None
        if isinstance(expected, dict):
            one = _first(expected, "one_sigma")
            ref = _first(price, "futures", "cfd")
            if one is not None and ref is not None and one > 0:
                three = 3.0 * one
                self.ledger.add(Evidence("distribution.implied_3sd", "DISTRIBUTION",
                    "Implied ±3σ range", {
                        "reference": ref, "one_sigma": one, "three_sigma": three,
                        "low": ref - three, "high": ref + three,
                        "method": expected.get("method") or "UNKNOWN",
                    }, "Distribution-extreme context, not a forecast.",
                    provenance=("market_state.quant_metrics.volatility.expected_range",)))
                if current is not None:
                    z = (current - ref) / one
                    self.ledger.add(Evidence("distribution.implied_z", "DISTRIBUTION",
                        "Implied z-location", round(z, 4),
                        "Current location in implied sigma units.",
                        polarity="UPPER_TAIL" if z >= 2 else "LOWER_TAIL" if z <= -2 else "CENTRAL",
                        provenance=("market_state.price", "market_state.quant_metrics")))

        poc = _first(auction, "poc")
        vah = _first(auction, "vah")
        val = _first(auction, "val")
        if any(x is not None for x in (poc, vah, val)):
            location = "UNKNOWN"
            if current is not None and vah is not None and val is not None:
                location = "ABOVE_VALUE" if current > vah else "BELOW_VALUE" if current < val else "INSIDE_VALUE"
            self.ledger.add(Evidence("auction.profile", "AUCTION", "TPO / auction profile", {
                "poc": poc, "vah": vah, "val": val, "location": location,
                "mode": auction.get("mode"), "approximation": auction.get("approximation"),
            }, "Acceptance/value context, not a trigger.", polarity=location,
            provenance=("market_state.auction",)))

        tpo = auction.get("tpo")
        if isinstance(tpo, list) and tpo:
            self.ledger.add(Evidence("auction.tpo_distribution", "AUCTION", "TPO distribution", tpo,
                "Price-time distribution context.", provenance=("market_state.auction.tpo",)))

        aggression = (order_flow.get("aggression") or {})
        if aggression:
            delta = _num(aggression.get("delta"))
            self.ledger.add(Evidence("flow.aggression", "MICROSTRUCTURE", "Trade aggression", {
                "buy": _num(aggression.get("buy")),
                "sell": _num(aggression.get("sell")),
                "delta": delta,
                "trade_count": aggression.get("trade_count"),
                "total": _num(aggression.get("total")),
                "price_displacement": _num(aggression.get("price_displacement")),
            }, "Observed aggression and displacement.",
            polarity="BUY_AGGRESSION" if delta and delta > 0 else "SELL_AGGRESSION" if delta and delta < 0 else "NEUTRAL_OR_UNKNOWN",
            provenance=("market_state.order_flow.aggression",)))

        blocks = self._blocks()
        if blocks:
            self.ledger.add(Evidence("flow.blocks", "MICROSTRUCTURE", "Adaptive block candidates", blocks,
                "Large-trade candidates relative to the local observed size distribution.",
                provenance=("raw_series.order_flow.trades",)))

        timing = {}
        for tf in ("h4", "h1", "m15", "m5", "m1"):
            row = technical.get(tf) or {}
            if row.get("trend") or row.get("bos"):
                timing[tf] = {
                    "trend": row.get("trend"), "bos": row.get("bos"),
                    "momentum_5": _num(row.get("momentum_5")),
                    "vwap": _num(row.get("vwap")),
                }
        if timing:
            self.ledger.add(Evidence("technical.mtf", "TECHNICAL_TIMING", "MTF technical state",
                timing, "Timing/confirmation context.", provenance=("market_state.technical",)))

        news = self.market.get("news") or []
        fresh = [x for x in news if isinstance(x, dict)
                 and _upper(x.get("freshness")) in {"FRESH", "RECENT"}
                 and _upper(x.get("relevance")) in {"HIGH", "CRITICAL"}]
        if fresh:
            self.ledger.add(Evidence("news.fresh_high", "EVENT", "Fresh high-relevance news", fresh,
                "Recent events may invalidate stale scenarios.",
                polarity="EVENT_RISK", provenance=("market_state.news",)))

        for key, family, label in (
            ("social_intelligence", "CROWD", "Social intelligence"),
            ("youtube_intelligence", "CROWD", "YouTube intelligence"),
            ("tiktok_intelligence", "CROWD", "TikTok intelligence"),
            ("facebook_intelligence", "CROWD", "Facebook intelligence"),
            ("web_intelligence", "EVENT", "Web intelligence"),
            ("narrative_intelligence", "CROWD", "Narrative intelligence"),
        ):
            value = self.raw.get(key)
            if value:
                self.ledger.add(Evidence("external." + key, family, label, value,
                    "Optional external evidence. Upstream adapters must enforce authorization and timestamps.",
                    provenance=("raw_series." + key,)))

    def _relationships(self) -> None:
        auction = self.ledger.get("auction.profile")
        z = self.ledger.get("distribution.implied_z")
        flow = self.ledger.get("flow.aggression")
        blocks = self.ledger.get("flow.blocks")
        gamma = self.ledger.get("options.gamma")
        structure = self.ledger.get("structure.direction")
        skew = self.ledger.get("vol.skew")
        news = self.ledger.get("news.fresh_high")

        if auction and z:
            zv = _num(z.value)
            loc = (auction.value or {}).get("location")
            if zv is not None and abs(zv) >= 2 and loc in {"ABOVE_VALUE", "BELOW_VALUE"}:
                self.relationships.append(Relationship(
                    "auction_distribution_extreme", "EXTREME_LOCATION",
                    ("auction.profile", "distribution.implied_z"),
                    "Price is outside value and beyond about 2σ; avoid treating extension as automatic continuation.",
                    "HIGH", "BULLISH" if zv > 0 else "BEARISH"))

        if flow and blocks:
            delta = _num((flow.value or {}).get("delta"))
            displacement = _num((flow.value or {}).get("price_displacement"))
            count = _num((blocks.value or {}).get("count"))
            if delta and displacement is not None and count and abs(displacement) <= 0:
                self.relationships.append(Relationship(
                    "block_absorption_candidate", "ABSORPTION_CANDIDATE",
                    ("flow.aggression", "flow.blocks"),
                    "Aggressive blocks with negligible displacement may indicate absorption; reversal is not confirmed.",
                    "HIGH", "BULLISH" if delta > 0 else "BEARISH"))

        if flow and gamma:
            delta = _num((flow.value or {}).get("delta"))
            if delta and _num((gamma.value or {}).get("net_gex")) is not None:
                self.relationships.append(Relationship(
                    "flow_gamma_interaction", "FLOW_X_GAMMA",
                    ("flow.aggression", "options.gamma"),
                    "Flow must be interpreted through gamma regime; negative gamma raises displacement sensitivity.",
                    "MEDIUM", "BULLISH" if delta > 0 else "BEARISH"))

        if structure and skew:
            self.relationships.append(Relationship(
                "structure_x_skew", "TAIL_RISK_CONTEXT",
                ("structure.direction", "vol.skew"),
                "Skew qualifies asymmetric risk around the structural thesis; it is not a reversal vote.",
                "MEDIUM", _dir(structure.value)))

        if news and structure:
            self.relationships.append(Relationship(
                "event_x_structure", "EVENT_REGIME_INTERACTION",
                ("news.fresh_high", "structure.direction"),
                "A fresh high-relevance event can invalidate pre-event structure; require post-event price confirmation.",
                "HIGH", _dir(structure.value)))

    def _conflicts(self) -> None:
        structure = self.ledger.get("structure.direction")
        auction = self.ledger.get("auction.profile")
        flow = self.ledger.get("flow.aggression")
        skew = self.ledger.get("vol.skew")
        if structure and auction:
            d = _dir(structure.value)
            loc = (auction.value or {}).get("location")
            if d == "BULLISH" and loc == "BELOW_VALUE":
                self.conflicts.append(Conflict("bullish_below_value", "HIGH",
                    ("structure.direction", "auction.profile"),
                    "Bullish higher-timeframe structure but price is below value.",
                    "Require value re-entry/acceptance before activating long scenario."))
            elif d == "BEARISH" and loc == "ABOVE_VALUE":
                self.conflicts.append(Conflict("bearish_above_value", "HIGH",
                    ("structure.direction", "auction.profile"),
                    "Bearish higher-timeframe structure but price is above value.",
                    "Require value rejection/breakdown before activating short scenario."))

        if structure and flow:
            d = _dir(structure.value)
            delta = _num((flow.value or {}).get("delta"))
            if d == "BULLISH" and delta is not None and delta < 0:
                self.conflicts.append(Conflict("bullish_sell_flow", "MEDIUM",
                    ("structure.direction", "flow.aggression"),
                    "Bullish structure conflicts with sell-heavy short-horizon flow.",
                    "Require price confirmation."))
            elif d == "BEARISH" and delta is not None and delta > 0:
                self.conflicts.append(Conflict("bearish_buy_flow", "MEDIUM",
                    ("structure.direction", "flow.aggression"),
                    "Bearish structure conflicts with buy-heavy short-horizon flow.",
                    "Require price confirmation."))

        if skew and abs(_num(skew.value) or 0) > 0:
            self.conflicts.append(Conflict("skew_is_risk_context", "LOW", ("vol.skew",),
                "Skew is asymmetric risk information, not a BUY/SELL instruction.",
                "Use for tail-risk qualification and sizing research."))

        crowd = next((x for x in self.ledger.items if x.family == "CROWD"), None)
        if structure and crowd and isinstance(crowd.value, dict):
            cd = _dir(crowd.value.get("direction"))
            sd = _dir(structure.value)
            if cd != "UNKNOWN" and sd != "UNKNOWN" and cd != sd:
                self.conflicts.append(Conflict("crowd_market_divergence", "MEDIUM",
                    (structure.evidence_id, crowd.evidence_id),
                    "Crowd narrative diverges from deterministic market structure.",
                    "Require actual price/flow transmission before changing scenario."))

    def _scenarios(self, direction: str) -> list[dict[str, Any]]:
        setups = (self.market.get("action_zones") or {}).get("setups") or {}
        def make(side: str, primary: str, fallback: str, active: bool) -> dict[str, Any]:
            setup = setups.get(primary) or setups.get(fallback) or {}
            return {
                "id": side + "_CONDITIONAL",
                "side": side,
                "state": "PRIMARY_WATCH" if active else "ALTERNATIVE_WATCH",
                "trigger": _num(setup.get("zone_price") or setup.get("trigger")),
                "invalidation": _num(setup.get("invalidation") or setup.get("stop")),
                "event_required": setup.get("event_required"),
                "evidence_required": ["PRICE_CONFIRMATION", "AUCTION_CONFIRMATION", "MICROSTRUCTURE_CONFIRMATION"],
                "execution_authority": "NONE",
            }
        return [
            make("LONG", "breakout_retest_long", "reversal_long", direction == "BULLISH"),
            make("SHORT", "breakout_retest_short", "reversal_short", direction == "BEARISH"),
        ]

    def _structural_direction(self) -> str:
        d = self.market.get("decision_framework") or self.market.get("decision") or {}
        for key in ("structural_bias", "bias", "direction"):
            value = _dir(d.get(key))
            if value != "UNKNOWN":
                return value
        t = self.market.get("technical") or {}
        h4 = _dir((t.get("h4") or {}).get("trend"))
        h1 = _dir((t.get("h1") or {}).get("trend"))
        return h4 if h4 != "UNKNOWN" and h4 == h1 else h4 if h4 != "UNKNOWN" else h1

    def _location(self) -> str:
        price = _first(self.market.get("price") or {}, "cfd", "futures")
        levels = self.market.get("levels") or {}
        support = _first(levels, "support_current", "support")
        resistance = _first(levels, "resistance_current", "resistance")
        if price is None or support is None or resistance is None:
            return "UNKNOWN"
        return "ABOVE_RESISTANCE" if price > resistance else "BELOW_SUPPORT" if price < support else "INSIDE_STRUCTURE"

    def _blocks(self) -> dict[str, Any] | None:
        raw = self.raw.get("order_flow") or {}
        rows = raw.get("trades") if isinstance(raw, dict) else None
        if not isinstance(rows, list):
            return None
        obs: list[tuple[str, float]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            size = _num(row.get("size") if row.get("size") is not None else row.get("quantity"))
            if size is None or size <= 0:
                continue
            side = _upper(row.get("aggressor_side") or row.get("side"))
            obs.append((side, size))
        if len(obs) < 8:
            return None
        sizes = sorted(x[1] for x in obs)
        index = min(len(sizes) - 1, max(0, ceil(0.99 * (len(sizes) - 1))))
        threshold = sizes[index]
        blocks = [x for x in obs if x[1] >= threshold]
        buy = sum(size for side, size in blocks if side in {"BUY", "B"})
        sell = sum(size for side, size in blocks if side in {"SELL", "S"})
        return {
            "count": len(blocks),
            "threshold": threshold,
            "buy_size": buy,
            "sell_size": sell,
            "net": buy - sell,
            "side_bias": "BUY" if buy > sell else "SELL" if sell > buy else "BALANCED",
        }

    def _coverage(self) -> dict[str, Any]:
        groups = {
            "market_structure": {"PRICE_STRUCTURE", "AUCTION", "DISTRIBUTION", "MICROSTRUCTURE", "TECHNICAL_TIMING"},
            "options": {"OPTIONS_POSITIONING", "VOLATILITY"},
            "context": {"EVENT"},
            "external": {"CROWD"},
        }
        present = {x.family for x in self.ledger.items}
        return {
            name: {
                "families_present": sorted(present & families),
                "complete": families <= present,
            }
            for name, families in groups.items()
        }


def build_evidence_fusion(state: dict[str, Any]) -> dict[str, Any]:
    return EvidenceFusionEngine(state).build()
