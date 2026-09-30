from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from math import isfinite

class MarketDataStatus(str, Enum):
    VALID = "VALID"
    OFFICIAL = "OFFICIAL"
    PRELIMINARY = "PRELIMINARY"
    STALE = "STALE"
    INCOMPLETE = "INCOMPLETE"
    UNAVAILABLE = "UNAVAILABLE"

class RightsStatus(str, Enum):
    APPROVED = "APPROVED"
    LICENSE_REQUIRED = "LICENSE_REQUIRED"
    LEGAL_REVIEW_REQUIRED = "LEGAL_REVIEW_REQUIRED"
    DENIED = "DENIED"

@dataclass(frozen=True)
class CommercialMarketStateEnvelope:
    symbol: str
    as_of: datetime
    publication_time: datetime | None
    availability_time: datetime | None
    ingestion_time: datetime
    data_status: MarketDataStatus | str
    data_quality: float
    data_age_seconds: float | None
    dataset_version: str
    calculation_version: str
    rights_status: RightsStatus | str

    def validate(self, *, now: datetime | None = None, max_age_seconds: float = 120.0, clock_skew_seconds: float = 5.0) -> tuple[bool, tuple[str, ...]]:
        errors: list[str] = []
        current = now or datetime.now(timezone.utc)
        for name, value in (
            ("as_of", self.as_of),
            ("ingestion_time", self.ingestion_time),
            ("publication_time", self.publication_time),
            ("availability_time", self.availability_time),
        ):
            if value is not None and value.tzinfo is None:
                errors.append(f"{name.upper()}_MUST_BE_TIMEZONE_AWARE")
        if current.tzinfo is None:
            errors.append("NOW_MUST_BE_TIMEZONE_AWARE")
            return False, tuple(errors)
        if self.as_of > current + timedelta(seconds=clock_skew_seconds):
            errors.append("AS_OF_IN_FUTURE")
        if self.ingestion_time > current + timedelta(seconds=clock_skew_seconds):
            errors.append("INGESTION_TIME_IN_FUTURE")
        if self.publication_time is None:
            errors.append("PUBLICATION_TIME_REQUIRED")
        if self.availability_time is None:
            errors.append("AVAILABILITY_TIME_REQUIRED")
        if self.publication_time and self.availability_time:
            if self.availability_time < self.publication_time:
                errors.append("AVAILABILITY_BEFORE_PUBLICATION")
            if self.publication_time > self.as_of:
                errors.append("PUBLICATION_AFTER_AS_OF")
            if self.availability_time > self.as_of:
                errors.append("AVAILABILITY_AFTER_AS_OF")
        if str(self.data_status) not in {MarketDataStatus.VALID.value, MarketDataStatus.OFFICIAL.value}:
            errors.append(f"DATA_STATUS_NOT_CUSTOMER_VALID:{self.data_status}")
        if not isfinite(self.data_quality) or not 0.0 <= self.data_quality <= 1.0:
            errors.append("DATA_QUALITY_OUT_OF_RANGE")
        if self.data_age_seconds is None:
            errors.append("DATA_AGE_REQUIRED")
        elif not isfinite(self.data_age_seconds) or self.data_age_seconds < 0:
            errors.append("DATA_AGE_INVALID")
        elif self.data_age_seconds > max_age_seconds:
            errors.append("DATA_TOO_OLD")
        if str(self.rights_status) != RightsStatus.APPROVED.value:
            errors.append(f"DATA_RIGHTS_NOT_APPROVED:{self.rights_status}")
        if not self.symbol.strip():
            errors.append("SYMBOL_REQUIRED")
        if not self.dataset_version.strip():
            errors.append("DATASET_VERSION_REQUIRED")
        if not self.calculation_version.strip():
            errors.append("CALCULATION_VERSION_REQUIRED")
        return not errors, tuple(errors)
