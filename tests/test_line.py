from src import line


def test_line_analysis_is_analysis_first_and_plain_language():
    parsed = {
        "future_price": 4136.70,
        "cfd_price": 4134.78,
        "basis_diff": 1.92,
        "dte": 0.55,
        "vol": 29.17,
        "raw_series": {
            "market_state": {
                "flow": {
                    "oi_put": 1209,
                    "oi_call": 491,
                    "oi_change_put": 188,
                    "oi_change_call": 189,
                    "source_churn_total": 23.83,
                },
                "volatility": {"iv": 29.17, "iv_change_1h": 0.8},
                "gamma": {
                    "net_gex": -87310948.74,
                    "put_wall": 4123.08,
                    "call_wall": 4223.08,
                },
                "technical": {
                    "h4": {"trend": "bearish"},
                    "h1": {"trend": "mixed"},
                },
            }
        },
    }
    ai = {
        "analysis_status": "DEGRADED",
        "bias": "WAIT",
        "market_regime": "EVENT",
        "market_overview": "ราคายังแกว่งใกล้ระดับสำคัญ",
        "why": "OI activity สองฝั่งเพิ่มขึ้น แต่ aggressor direction ยังไม่ชัด",
        "financial_engineering": "Negative Gamma เพิ่มโอกาสให้การเคลื่อนไหวแรงขึ้น",
        "market_microstructure": "H4 bearish แต่กรอบสั้นยังไม่ยืนยัน",
        "macro": "มีข่าวสำคัญที่ตลาดกำลังรอ",
    }
    message = line.format_message(parsed, ai)
    assert "MARKET READ" in message
    assert "VOLATILITY" in message
    assert "FLOW STATEMENT" in message
    assert "OI POSITIONING" in message
    assert "Current OI" not in message
    assert "OI Change" not in message
    assert "มีการเพิ่มสถานะทั้ง Put และ Call ใกล้เคียงกัน" in message
