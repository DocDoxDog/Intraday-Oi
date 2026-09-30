from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

def distinct_users(events, *, start: datetime, end: datetime) -> int:
    users = set()
    for event in events:
        when = event.occurred_at
        if when.tzinfo is None:
            continue
        if start <= when < end and event.user_id:
            users.add(event.user_id)
    return len(users)

def event_counts(events, *, start: datetime, end: datetime) -> dict[str, int]:
    counts = Counter()
    for event in events:
        if start <= event.occurred_at < end:
            counts[event.event_name] += 1
    return dict(counts)