from __future__ import annotations

import importlib.util
import math
import os
from pathlib import Path


SYMBOLS = ("GC", "SI", "CL", "ES", "NQ")


def _load_ai_trader_gex():
    explicit = os.environ.get("AI_TRADER_GEX_PATH")
    path = (
        Path(explicit)
        if explicit
        else Path(__file__).resolve().parents[2]
        / "Ai-trader"
        / "ai_gold"
        / "data"
        / "options"
        / "gex.py"
    )
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("ai_trader_gex_legacy", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _case(symbol: str, idx: int, scenario: str = "normal"):
    iv = {"normal": 25.0, "high_vol": 60.0}.get(scenario, 25.0)
    dte = {"normal": 14.0, "high_vol": 3.0, "expiration": 1.0}.get(scenario, 14.0)
    return {
        "symbol": symbol,
        "futures": 4000.0 + idx * 100.0,
        "strike": 4000.0 + idx * 100.0,
        "vol": iv,
        "call_oi": 75.0 + idx * 10.0,
        "put_oi": 60.0 + idx * 8.0,
        "dte_days": dte,
        "multiplier": 10.0 + idx,
    }


def test_canonical_matches_intraday_legacy_path():
    from quant.exposure.gex import calculate_gex
    from src.gex import calculate_gex as legacy

    for scenario in ("normal", "high_vol", "expiration"):
        for idx, symbol in enumerate(SYMBOLS):
            c = _case(symbol, idx, scenario)
            rows = [{
                "strike": c["strike"],
                "vol": c["vol"],
                "oiCall": c["call_oi"],
                "oiPut": c["put_oi"],
            }]
            new = calculate_gex(
                rows,
                c["futures"],
                dte_days=c["dte_days"],
                multiplier=c["multiplier"],
                underlying=symbol,
            )
            old = legacy(
                rows,
                c["futures"],
                dte_days=c["dte_days"],
                multiplier=c["multiplier"],
                underlying=symbol,
            )
            assert new == old


def test_canonical_matches_ai_trader_legacy():
    ai = _load_ai_trader_gex()
    assert ai is not None, "AI_TRADER_GEX_PATH must point to legacy GEX for parity CI"

    from quant.exposure.gex import calculate_gex

    for scenario in ("normal", "high_vol", "expiration"):
        for idx, symbol in enumerate(SYMBOLS):
            c = _case(symbol, idx, scenario)
            for option_type, oi in (("CALL", c["call_oi"]), ("PUT", c["put_oi"])):
                row = ai.OptionRow(
                    expiry_years=c["dte_days"] / 365.0,
                    strike=c["strike"],
                    futures_price=c["futures"],
                    implied_vol=c["vol"] / 100.0,
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
                        "vol": c["vol"],
                        "oiCall": oi if option_type == "CALL" else 0,
                        "oiPut": oi if option_type == "PUT" else 0,
                    }],
                    c["futures"],
                    dte_days=c["dte_days"],
                    multiplier=c["multiplier"],
                    underlying=symbol,
                )
                expected = (
                    canonical["rows"][0]["call_gex"]
                    if option_type == "CALL"
                    else canonical["rows"][0]["put_gex"]
                )
                assert math.isclose(old.gex, expected, rel_tol=1e-12, abs_tol=1e-12)


def test_missing_data_and_zero_oi_are_explicit():
    from quant.exposure.gex import calculate_gex

    missing = calculate_gex(
        [{"strike": 4300, "oiCall": 100, "oiPut": 100}],
        4300,
        dte_days=3,
    )
    assert missing["status"] == "unavailable"

    zero = calculate_gex(
        [{"strike": 4300, "gamma": 0.001, "oiCall": 0, "oiPut": 0}],
        4300,
        dte_days=3,
    )
    assert zero["status"] == "ok"
    assert zero["rows"][0]["net_gex"] == 0
