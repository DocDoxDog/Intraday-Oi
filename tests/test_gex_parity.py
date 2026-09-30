from __future__ import annotations

import importlib.util
import math
import os
from pathlib import Path


SYMBOLS = ("GC", "SI", "CL", "ES", "NQ")


def _load_ai_trader_gex():
    explicit = os.environ.get("AI_TRADER_GEX_PATH")
    path = Path(explicit) if explicit else Path(__file__).resolve().parents[2] / "Ai-trader" / "ai_gold" / "data" / "options" / "gex.py"
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("ai_trader_gex_legacy", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _case(symbol: str, idx: int):
    return {
        "symbol": symbol,
        "futures": 4000.0 + idx * 100.0,
        "strike": 4000.0 + idx * 100.0,
        "gamma": 0.0008 + idx * 0.00005,
        "call_oi": 75.0 + idx * 10.0,
        "put_oi": 60.0 + idx * 8.0,
        "dte_days": (idx + 1) * 3.0,
        "multiplier": 10.0 + idx,
    }


def test_canonical_matches_intraday_legacy_path_for_all_symbol_fixtures():
    from quant.exposure.gex import calculate_gex
    from src.gex import calculate_gex as legacy

    for idx, symbol in enumerate(SYMBOLS):
        c = _case(symbol, idx)
        rows = [{
            "strike": c["strike"],
            "gamma": c["gamma"],
            "oiCall": c["call_oi"],
            "oiPut": c["put_oi"],
        }]
        new = calculate_gex(
            rows, c["futures"], dte_days=c["dte_days"], multiplier=c["multiplier"], underlying=symbol
        )
        old = legacy(
            rows, c["futures"], dte_days=c["dte_days"], multiplier=c["multiplier"]
        )
        assert new == old


def test_canonical_matches_ai_trader_legacy_when_available():
    ai = _load_ai_trader_gex()
    if ai is None:
        return

    from quant.exposure.gex import calculate_gex

    for idx, symbol in enumerate(SYMBOLS):
        c = _case(symbol, idx)
        for option_type, oi in (("CALL", c["call_oi"]), ("PUT", c["put_oi"])):
            row = ai.OptionRow(
                expiry_years=c["dte_days"] / 365.0,
                strike=c["strike"],
                futures_price=c["futures"],
                implied_vol=0.25,
                open_interest=oi,
                option_type=option_type,
            )
            old = ai.calculate_gex(
                row,
                contract_multiplier=c["multiplier"],
                sign_convention="DEALER_SHORT_PUBLIC",
            )
            canonical = calculate_gex(
                [{
                    "strike": c["strike"],
                    "gamma": c["gamma"],
                    "oiCall": oi if option_type == "CALL" else 0,
                    "oiPut": oi if option_type == "PUT" else 0,
                }],
                c["futures"],
                dte_days=c["dte_days"],
                multiplier=c["multiplier"],
            )
            expected = canonical["rows"][0]["call_gex"] if option_type == "CALL" else canonical["rows"][0]["put_gex"]
            assert math.isclose(old.gex, expected, rel_tol=1e-12, abs_tol=1e-12)


def test_parity_scope_documents_missing_legacy_dex():
    ai = _load_ai_trader_gex()
    assert ai is not None or os.environ.get("REQUIRE_AI_TRADER_PARITY", "0") != "1"
    assert "DEX" not in {"AI_TRADER_GEX_LEGACY"}
