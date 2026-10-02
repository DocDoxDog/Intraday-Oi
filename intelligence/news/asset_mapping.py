from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AssetMapping:
    asset: str
    direction: str
    confidence: float
    evidence: tuple[str, ...]


_RULES = (
    ("CPI", ("CPI", "consumer price index"), ("GOLD", "USD", "NASDAQ")),
    ("OPEC", ("OPEC", "production cut", "production increase"), ("USOIL", "UKOIL")),
    ("FED", ("FED", "FOMC", "Federal Reserve"), ("GOLD", "USD", "NASDAQ")),
    ("ECB", ("ECB", "European Central Bank"), ("EURUSD", "DXY")),
    ("BOJ", ("BOJ", "Bank of Japan"), ("USDJPY", "NIKKEI")),
    ("GEOPOLITICAL", ("WAR", "CONFLICT", "MISSILE", "AIRSTRIKE", "SANCTION", "CEASEFIRE", "MILITARY", "INVASION", "ATTACK", "HOSTILITIES", "RED SEA", "HORMUZ"), ("GOLD", "USD", "USOIL", "UKOIL")),
)


def map_assets(headline: str, body: str = "") -> tuple[AssetMapping, ...]:
    text = f"{headline} {body}".upper()
    out: list[AssetMapping] = []
    for category, keywords, assets in _RULES:
        if any(keyword.upper() in text for keyword in keywords):
            for asset in assets:
                out.append(
                    AssetMapping(
                        asset=asset,
                        direction="UNCERTAIN",
                        confidence=0.35,
                        evidence=(f"keyword_match:{category}", "direction_not_observed"),
                    )
                )
    dedup = {x.asset: x for x in out}
    return tuple(dedup.values())
