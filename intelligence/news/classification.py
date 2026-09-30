from __future__ import annotations


_CATEGORY_KEYWORDS = {
    "MACRO": ("CPI", "PPI", "GDP", "PAYROLL", "NONFARM", "INFLATION", "JOBS"),
    "CENTRAL_BANK": ("FED", "FOMC", "ECB", "BOJ", "RATE DECISION", "CENTRAL BANK"),
    "ENERGY": ("OPEC", "CRUDE", "OIL", "PRODUCTION CUT", "SUPPLY DISRUPTION"),
    "GEOPOLITICAL": ("SANCTION", "WAR", "CONFLICT", "MILITARY", "CEASEFIRE"),
    "MARKET_STRUCTURE": ("EXCHANGE HALT", "TRADING HALT", "CIRCUIT BREAKER"),
}


def classify(headline: str, body: str = "") -> tuple[str, tuple[str, ...]]:
    text = f"{headline} {body}".upper()
    for category, keywords in _CATEGORY_KEYWORDS.items():
        matches = tuple(keyword for keyword in keywords if keyword in text)
        if matches:
            return category, matches
    return "GENERAL", ()
