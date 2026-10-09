from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any


class NewsSourceAdapter:
    """Small injectable adapter; network collection remains provider-owned."""

    def __init__(self, source: str, collect_fn: Callable[[], Iterable[dict[str, Any]]]):
        if not str(source).strip() or not callable(collect_fn):
            raise ValueError("INVALID_NEWS_SOURCE_ADAPTER")
        self.source = str(source).strip()
        self._collect_fn = collect_fn

    def collect(self) -> list[dict[str, Any]]:
        rows = self._collect_fn()
        return [dict(row) for row in rows if isinstance(row, dict)]
