from src.event_outcome_engine import measure_outcome
from src.market_flow_engine import _bar_event, build_conditional_path


def t(minutes=0):
    return f"2026-10-08T10:{minutes:02d}:00+00:00"


def test_wick_does_not_count_as_break():
    assert _bar_event({"high": 101, "low": 99, "close": 99.8}, 100, "UP") == "REJECT"


def test_close_acceptance_counts_as_break():
    assert _bar_event({"high": 101, "low": 99.9, "close": 100.2}, 100, "UP") == "BREAK_ACCEPT"


def test_conditional_path_uses_observed_nodes_only():
    path = build_conditional_path(100, [{"level": 100}, {"level": 105}, {"level": 95}])
    assert path["upper_node"]["level"] == 105
    assert path["lower_node"]["level"] == 95
    assert path["next_up"] is None
    assert path["next_down"] is None


def test_outcome_excludes_event_bar_and_measures_forward_move():
    event = {
        "event_time": t(),
        "level": 100,
        "direction": "UP",
        "evidence": {"current_price": 100},
    }
    bars = [
        {"bar_time": t(), "open": 100, "high": 110, "low": 90, "close": 100},
        {"bar_time": t(5), "open": 100, "high": 102, "low": 99, "close": 101},
        {"bar_time": t(10), "open": 101, "high": 104, "low": 100, "close": 103},
    ]
    result = measure_outcome(event, bars, nodes=[{"level": 104}], horizon_seconds=900)
    assert result["forward_return"] == 0.03
    assert result["mfe"] == 0.04
    assert result["mae"] == -0.01
    assert result["next_node_hit"] == 104
    assert result["time_to_next_node_seconds"] == 600


def test_conditional_path_keeps_source_bar_time_for_event_persistence():
    path = build_conditional_path(
        100,
        [{"level": 100}, {"level": 105}, {"level": 95}],
        recent_bars=[{"datetime": "2026-10-08T10:00:00+00:00", "close": 100},
                     {"datetime": "2026-10-08T10:05:00+00:00", "high": 106, "low": 99, "close": 105.2}],
    )
    assert path["observed_last_event"] == "BREAK_ACCEPT"
    assert path["observed_event_time"] == "2026-10-08T10:05:00+00:00"
