from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

from intelligence.metrics_aggregation import distinct_users, event_counts


def test_metrics_aggregate_by_time_window():
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    events = [
        SimpleNamespace(occurred_at=start + timedelta(hours=1), user_id='u1', event_name='view'),
        SimpleNamespace(occurred_at=start + timedelta(hours=2), user_id='u2', event_name='view'),
        SimpleNamespace(occurred_at=start + timedelta(hours=3), user_id='u1', event_name='click'),
    ]
    assert distinct_users(events, start=start, end=start + timedelta(days=1)) == 2
    assert event_counts(events, start=start, end=start + timedelta(days=1)) == {'view': 2, 'click': 1}