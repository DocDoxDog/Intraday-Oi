"""Compatibility facade for the canonical contract model.

New consumers should import from quant.contracts. This module remains to avoid
breaking existing callers during the migration window.
"""

from quant.contracts import (
    Contract,
    Expiration,
    Future,
    Instrument,
    OptionContract,
    OptionType,
    Strike,
    canonical_id,
    normalize_option_type,
)

__all__ = [
    "Contract",
    "OptionContract",
    "OptionType",
    "Instrument",
    "Future",
    "Expiration",
    "Strike",
    "canonical_id",
    "normalize_option_type",
]
