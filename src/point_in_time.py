"""Point-in-time data integrity guards.

These checks fail closed when an evaluated event uses future information.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable


def parse_ts(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def assert_not_future(observed_at: Any, event_time: Any, field: str = "observed_at") -> None:
    observed = parse_ts(observed_at)
    event = parse_ts(event_time)
    if observed is None or event is None:
        raise ValueError(f"PIT_FAIL:{field}:missing_timestamp")
    if observed > event:
        raise ValueError(f"PIT_FAIL:{field}:future_data")


def validate_snapshot(snapshot: dict[str, Any], event_time: Any) -> list[str]:
    issues: list[str] = []
    event = parse_ts(event_time)
    if event is None:
        return ["missing_event_time"]
    for key in ("as_of", "observed_at", "captured_at", "retrieved_at", "published_at"):
        if key in snapshot and snapshot.get(key) not in (None, ""):
            try:
                assert_not_future(snapshot[key], event, key)
            except ValueError as exc:
                issues.append(str(exc))
    for i, item in enumerate(snapshot.get("news") or []):
        if not isinstance(item, dict):
            continue
        published = parse_ts(item.get("published_at"))
        if published and published > event:
            issues.append(f"PIT_FAIL:news[{i}]:published_after_event")
    for bucket in ("structural_nodes", "options_nodes", "gamma_nodes", "liquidity_nodes"):
        for i, node in enumerate(snapshot.get(bucket) or []):
            if not isinstance(node, dict):
                continue
            observed = node.get("observed_at") or node.get("as_of")
            if observed:
                try:
                    assert_not_future(observed, event, f"{bucket}[{i}]")
                except ValueError as exc:
                    issues.append(str(exc))
    return issues


def validate_dataset(rows: Iterable[dict[str, Any]], event_key: str = "event_time") -> dict[str, Any]:
    total = 0
    failed = 0
    failures: list[str] = []
    for row in rows:
        total += 1
        issues = validate_snapshot(row, row.get(event_key))
        if issues:
            failed += 1
            failures.extend(issues[:10])
    return {
        "rows": total,
        "failed_rows": failed,
        "failure_rate": failed / total if total else None,
        "status": "PASS" if failed == 0 and total > 0 else "FAIL" if failed > 0 else "DATA_INSUFFICIENT",
        "sample_failures": failures[:20],
    }
