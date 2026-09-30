from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any


def payload_checksum(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def dataset_version(
    *,
    source: str,
    source_version: str,
    checksum: str,
) -> str:
    return f"{source}:{source_version}:{checksum[:16]}"


@dataclass(frozen=True)
class RawMarketData:
    source: str
    payload: Any
    fetched_at: datetime
    source_file: str | None
    source_version: str
    checksum: str

    @classmethod
    def create(
        cls,
        *,
        source: str,
        payload: Any,
        source_file: str | None = None,
        source_version: str = "unknown",
        fetched_at: datetime | None = None,
    ) -> "RawMarketData":
        fetched = fetched_at or datetime.now(timezone.utc)
        if fetched.tzinfo is None:
            raise ValueError("FETCHED_AT_MUST_BE_TIMEZONE_AWARE")
        return cls(
            source=source,
            payload=payload,
            fetched_at=fetched,
            source_file=source_file,
            source_version=source_version,
            checksum=payload_checksum(payload),
        )

    @property
    def dataset_version(self) -> str:
        return dataset_version(
            source=self.source,
            source_version=self.source_version,
            checksum=self.checksum,
        )
