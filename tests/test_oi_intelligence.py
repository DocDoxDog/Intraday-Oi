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


def test_delta_exposure_unknown_when_greeks_missing():
    result = delta_adjusted_exposure([{"strike": 4300, "oiCall": 10, "oiPut": 5}])
    assert result["status"] == "UNKNOWN"
    assert result["net_delta_exposure"] is None
    assert result["rows"][0]["net_delta_exposure"] is None


def test_flow_unknown_when_delta_oi_is_missing():
    assert classify_flow({"oi_delta_call": None, "oi_delta_put": None})["label"] == "UNKNOWN"


def test_oi_positioning_does_not_invent_delta_without_baseline():
    from src.oi_positioning import enrich
    current = {"raw_series": {"oi_positioning_rows": [{"strike": 4300, "oiCall": 1804, "oiPut": 4212}]}}
    result = enrich(current, None)
    totals = result["raw_series"]["totals"]
    row = result["raw_series"]["oi_positioning_rows"][0]
    assert result["raw_series"]["oi_baseline"]["available"] is False
    assert row["oi_delta_call"] is None
    assert row["oi_delta_put"] is None
    assert totals["oi_delta_total"] is None
    assert totals["churn"] is None
