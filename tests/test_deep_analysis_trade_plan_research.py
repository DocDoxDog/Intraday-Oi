from datetime import datetime, timezone, timedelta

from src.historical_memory import _window_summary
from src.trade_plan_research import evaluate_plan


def _bar(dt, o, h, l, c):
    return {
        "bar_time": dt.isoformat(),
        "open": o,
        "high": h,
        "low": l,
        "close": c,
    }


def test_historical_memory_is_descriptive_and_point_in_time():
    as_of = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)
    rows = [
        _bar(as_of - timedelta(hours=3), 100, 102, 99, 101),
        _bar(as_of - timedelta(hours=2), 101, 103, 100, 102),
        _bar(as_of - timedelta(hours=1), 102, 104, 101, 103),
        # Future bar must never be part of the window.
        _bar(as_of + timedelta(hours=1), 103, 120, 90, 110),
    ]
    result = _window_summary(rows[:3], as_of=as_of, horizon="4H")
    assert result["status"] == "VALID"
    assert result["high"] == 104
    assert result["last"] == 103
    assert result["direction"] == "UP"


def test_trade_plan_outcome_stop_wins_same_bar():
    as_of = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)
    plan = {
        "observed_at": as_of.isoformat(),
        "side": "BUY",
        "entry": 100,
        "stop_loss": 98,
        "targets": [102],
    }
    bars = [
        _bar(as_of + timedelta(minutes=5), 100, 103, 97, 101),
    ]
    outcome = evaluate_plan(plan, bars, 900)
    assert outcome["entry_touched"] is True
    assert outcome["first_exit"] == "SL_AND_TP_SAME_BAR_CONSERVATIVE_SL"
    assert outcome["outcome_state"] == "STOP_LOSS"


def test_trade_plan_outcome_records_tp_when_target_hits_first():
    as_of = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)
    plan = {
        "observed_at": as_of.isoformat(),
        "side": "SELL",
        "entry": 100,
        "stop_loss": 102,
        "targets": [98, 96],
    }
    bars = [
        _bar(as_of + timedelta(minutes=5), 100, 100.5, 97.5, 98),
    ]
    outcome = evaluate_plan(plan, bars, 900)
    assert outcome["entry_touched"] is True
    assert outcome["tp1_hit"] is True
    assert outcome["outcome_state"] == "TAKE_PROFIT"
