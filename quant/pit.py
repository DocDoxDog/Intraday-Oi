from __future__ import annotations

from datetime import datetime
from typing import Iterable, TypeVar


T = TypeVar("T")


def is_available_at(record: T, decision_time: datetime) -> bool:
    if decision_time.tzinfo is None:
        raise ValueError("DECISION_TIME_MUST_BE_TIMEZONE_AWARE")
    availability = getattr(record, "availability_time", None)
    return availability is not None and availability <= decision_time


def require_available_at(records: Iterable[T], decision_time: datetime) -> list[T]:
    if decision_time.tzinfo is None:
        raise ValueError("DECISION_TIME_MUST_BE_TIMEZONE_AWARE")
    return [record for record in records if is_available_at(record, decision_time)]
