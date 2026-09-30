from datetime import datetime, timezone
from types import SimpleNamespace

from intelligence.alert_quality import AlertQualityMetrics
from intelligence.change_detector import detect_changes
from intelligence.report import build_daily_report


def state(price):
    return SimpleNamespace(
        symbol="GC", price=price, oi=100, oi_change=5, gex=10, dex=3, iv=20,
        realized_vol=18, positioning_regime="UNKNOWN", volatility_regime="NORMAL",
        data_status="VALID", data_quality=1.0, data_age_seconds=2,
        gamma_flip=99, call_wall=105, put_wall=95,
        dataset_version="d1", calculation_version="c1",
    )


def test_change_detector_reports_changed_price():
    changes = detect_changes(state(100), state(101))
    price = next(x for x in changes if x.field == "price")
    assert price.changed


def test_daily_report_contains_data_provenance():
    report = build_daily_report(market_state=state(100), news_rows=[], plan_rows=[])
    assert "DATA QUALITY" in report
    assert "dataset=d1" in report
    assert "calculation=c1" in report


def test_alert_quality_rates_do_not_divide_by_zero():
    metrics = AlertQualityMetrics(0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    assert metrics.muted_rate == 0.0
    assert metrics.duplicate_rate == 0.0