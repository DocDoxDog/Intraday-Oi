from src.market_flow_engine import build_conditional_path, build_price_memory, rank_structural_nodes


def test_no_synthetic_nodes():
    nodes = rank_structural_nodes(
        4121.65,
        [{"level":4134.5,"node_type":"CALL_WALL"},{"level":4114.5,"node_type":"LOCAL"}],
    )
    assert [x["level"] for x in nodes] == [4134.5, 4114.5]


def test_conditional_path_has_reclaim_and_break_accept():
    path = build_conditional_path(
        4121.65,
        [{"level":4134.5},{"level":4114.5},{"level":4100.0}],
    )
    assert path["upper_node"]["level"] == 4134.5
    assert path["lower_node"]["level"] == 4114.5
    assert any(x["condition_type"] == "RECLAIM" for x in path["transitions"])
    assert any(x["condition_type"] == "BREAK_ACCEPT" for x in path["transitions"])


def test_wick_does_not_become_break_accept():
    path = build_conditional_path(
        4121.65,
        [{"level":4134.5},{"level":4114.5}],
        recent_bars=[
            {"close":4125.0,"high":4136.0,"low":4123.0},
            {"close":4130.0,"high":4135.0,"low":4124.0},
        ],
    )
    upper_events=[x for x in path["transitions"] if x["condition_type"]=="BREAK_ACCEPT" and x["to"]==4134.5]
    assert upper_events
    assert upper_events[0]["observed_event"] == "REJECT"


def test_price_memory():
    m = build_price_memory(
        {"m5":[{"datetime":"2026-10-08 10:00:00","open":"1","high":"3","low":"0","close":"2"}]},
        2,
    )
    assert m["timeframes"]["m5"]["last_close"] == 2.0
