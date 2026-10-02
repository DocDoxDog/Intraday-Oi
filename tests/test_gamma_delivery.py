from src.gamma_chart import render_gamma_table
from src.telegram import format_message


def test_gamma_table_renderer_produces_png():
    matrix = {
        "columns": [
            {"code": "OGU6", "dte": 1.38, "observed_at": None},
            {"code": "G4RQ6", "dte": 2.38, "observed_at": None},
        ],
        "matrix": [
            {"strike": 4600.0, "OGU6": 10.0, "G4RQ6": -4.0},
            {"strike": 4610.0, "OGU6": None, "G4RQ6": 5.0},
        ],
        "totals": {"OGU6": 10.0, "G4RQ6": 1.0},
        "status": "VALID",
    }
    image = render_gamma_table(matrix)
    assert image[:8] == b"\x89PNG\r\n\x1a\n"


def test_telegram_mentions_multi_expiry_gamma():
    parsed = {
        "future_price": 4605,
        "cfd_price": 4601,
        "dte": 1.38,
        "raw_series": {
            "gex": {"status": "ok"},
            "multi_expiry_gamma": {"expiration_count": 7},
            "multi_expiry_gamma_zones": {
                "highest_positive_gamma": 4600,
                "highest_negative_gamma": 4550,
            },
        },
    }
    ai = {
        "market_overview": "test",
        "bull_case": "test",
        "bear_case": "test",
        "sideway_case": "test",
        "bias": "WAIT",
        "evidence_refs": [],
        "data_limitations": [],
    }
    message = format_message(parsed, ai)
    assert "7 expirations" in message
    assert "4600" in message


def test_gamma_table_uses_millions_per_one_percent_move():
    matrix = {
        "columns": [{"code": "OGU6", "dte": 1.0}],
        "matrix": [{"strike": 4600.0, "OGU6": 2_500_000.0}],
        "totals": {"OGU6": 2_500_000.0},
        "status": "VALID",
    }
    image = render_gamma_table(matrix)
    assert image[:8] == b"\x89PNG\r\n\x1a\n"
