from src.gamma_chart import (
    _compact_rows,
    _display_strike,
    render_gamma_table,
)
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
    from src import telegram
    parsed = {
        "future_price": 4605,
        "cfd_price": 4601,
        "dte": 1.38,
        "raw_series": {
            "gex": {"status": "ok"},
            "multi_expiry_gamma": {"columns": [{"code": f"E{i}"} for i in range(7)]},
            "multi_expiry_gamma_zones": {
                "highest_positive_gamma": 4600,
                "highest_negative_gamma": 4550,
            },
        },
    }
    ai = {
        "analysis_status": "CONFIRMED",
        "market_overview": "test",
        "bias": "WAIT",
        "levels": {"resistance_far":"-", "resistance_main":"-", "resistance_current":"-", "support_current":"-", "support_main":"-", "support_deep":"-"},
        "scenarios": {"bull":"test","bear":"test","sideway":"test"},
    }
    message = telegram._format_levels_message(parsed, ai)
    assert "GAMMA TERM STRUCTURE" in message
    assert "<b>7</b> expirations" in message
    assert "4,600.00" in message




def test_gamma_table_uses_millions_per_one_percent_move():
    matrix = {
        "columns": [{"code": "OGU6", "dte": 1.0}],
        "matrix": [{"strike": 4600.0, "OGU6": 2_500_000.0}],
        "totals": {"OGU6": 2_500_000.0},
        "status": "VALID",
    }
    image = render_gamma_table(matrix)
    assert image[:8] == b"\x89PNG\r\n\x1a\n"


def test_full_gamma_table_includes_all_available_strikes():
    from src.gamma_chart import render_gamma_table, render_gamma_table_full
    matrix = {
        "current_price": 4200,
        "columns": [
            {"code": "OG1V6", "dte": 0.34, "status": "OBSERVED"},
            {"code": "G1MV6", "dte": 1.34, "status": "OBSERVED"},
        ],
        "matrix": [
            {"strike": float(x), "OG1V6": 1_000_000, "G1MV6": -500_000}
            for x in range(4100, 4310, 5)
        ],
        "totals": {"OG1V6": 43_000_000, "G1MV6": -21_500_000},
        "status": "VALID",
    }
    compact = render_gamma_table(matrix)
    full = render_gamma_table_full(matrix)
    assert compact.startswith(b"\x89PNG")
    assert full.startswith(b"\x89PNG")
    assert len(full) > len(compact)



def test_compact_gamma_window_is_30_real_source_rows():
    matrix = {
        "current_price": 4200.0,
        "columns": [{"code": "OGV6", "dte": 0.5}],
        "matrix": [
            {"strike": float(x), "OGV6": 1_000_000.0}
            for x in range(4000, 4405, 5)
        ],
    }
    rows = _compact_rows(matrix)
    assert len(rows) == 30
    assert max(row["strike"] for row in rows) - min(row["strike"] for row in rows) == 145.0
    assert all(row in matrix["matrix"] for row in rows)


def test_gamma_price_column_converts_futures_strike_to_cfd():
    context = {
        "future_price": 4200.0,
        "cfd_price": 4175.0,
    }
    assert _display_strike(4250.0, context) == 4225.0


def test_gamma_renderer_accepts_snapshot_metadata():
    matrix = {
        "current_price": 4200.0,
        "columns": [{"code": "OGV6", "dte": 0.5}],
        "matrix": [
            {"strike": 4200.0, "OGV6": 1_000_000.0},
            {"strike": 4205.0, "OGV6": -500_000.0},
        ],
        "totals": {"OGV6": 500_000.0},
        "status": "VALID",
    }
    image = render_gamma_table(
        matrix,
        context={
            "observed_at": "2026-10-05T13:02:00+00:00",
            "future_price": 4200.0,
            "cfd_price": 4175.0,
            "basis_diff": 25.0,
            "iv": 15.5,
            "gex_change_1h": -2_000_000.0,
        },
    )
    assert image.startswith(b"\x89PNG")
