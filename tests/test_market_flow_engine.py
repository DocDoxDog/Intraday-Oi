from src.market_flow_engine import build_conditional_path, build_price_memory, rank_structural_nodes

def test_no_synthetic_nodes():
    nodes=rank_structural_nodes(4121.65, [{"level":4134.5,"node_type":"CALL_WALL"},{"level":4114.5,"node_type":"LOCAL"}])
    assert [x["level"] for x in nodes]==[4134.5,4114.5]

def test_conditional_path_has_reclaim():
    path=build_conditional_path(4121.65,[{"level":4134.5},{"level":4114.5},{"level":4100.0}])
    assert path["upper_node"]["level"]==4134.5
    assert path["lower_node"]["level"]==4114.5
    assert any(x["condition_type"]=="RECLAIM" for x in path["transitions"])

def test_price_memory():
    m=build_price_memory({"m5":[{"datetime":"2026-10-08 10:00:00","open":"1","high":"3","low":"0","close":"2"}]},2)
    assert m["timeframes"]["m5"]["last_close"]==2.0
