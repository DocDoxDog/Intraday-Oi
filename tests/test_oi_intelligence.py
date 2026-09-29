from src.oi_intelligence import delta_adjusted_exposure, classify_flow, oi_migration

def test_delta_adjusted_exposure():
    r=delta_adjusted_exposure([{"strike":4300,"oiCall":10,"oiPut":5,"callDelta":0.5,"putDelta":-0.4}])
    assert r["net_delta_exposure"]==300.0

def test_flow_unknown_without_price():
    assert classify_flow({"oi_delta_call":100,"oi_delta_put":0})["label"]=="UNKNOWN"

def test_migration():
    r=oi_migration([{"strike":4300,"oiCall":100},{"strike":4350,"oiCall":0}],
                   [{"strike":4300,"oiCall":50},{"strike":4350,"oiCall":50}])
    assert r["shifts"][0]["from_strike"]==4300
    assert r["shifts"][0]["to_strike"]==4350
