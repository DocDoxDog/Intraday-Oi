from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

from quant.contracts import OptionType


class DataStatus(str, Enum):
    VALID = "VALID"
    PRELIMINARY = "PRELIMINARY"
    OFFICIAL = "OFFICIAL"
    STALE = "STALE"
    INCOMPLETE = "INCOMPLETE"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class OIObservation:
    observation_id: str
    instrument_id: str
    expiration_id: str
    strike_id: str
    trade_date: date
    observation_time: datetime
    publication_time: datetime | None
    availability_time: datetime | None
    ingestion_time: datetime
    calculation_time: datetime | None
    option_type: OptionType
    oi: float
    oi_change: float | None
    volume: float | None
    source: str
    dataset_version: str
    data_status: DataStatus = DataStatus.VALID
    timezone: str = "UTC"

    def __post_init__(self) -> None:
        for name in (
            "observation_time",
            "publication_time",
            "availability_time",
            "ingestion_time",
            "calculation_time",
        ):
            value = getattr(self, name)
            if value is not None and value.tzinfo is None:
                raise ValueError(f"{name}_MUST_BE_TIMEZONE_AWARE")

        if self.oi < 0:
            raise ValueError("OI_MUST_BE_NON_NEGATIVE")

        if self.publication_time and self.availability_time:
            if self.availability_time < self.publication_time:
                raise ValueError("AVAILABILITY_BEFORE_PUBLICATION")

    def is_available_at(self, decision_time: datetime) -> bool:
        if decision_time.tzinfo is None:
            raise ValueError("DECISION_TIME_MUST_BE_TIMEZONE_AWARE")
        if self.availability_time is None:
            return False
        return self.availability_time <= decision_time


@dataclass(frozen=True)
class GreekObservation:
    option_id: str
    observation_time: datetime
    model: str
    calculation_version: str
    delta: float | None
    gamma: float | None
    theta: float | None
    vega: float | None
    implied_volatility: float | None
    iv_input_unit: str
    gamma_unit: str
    theta_unit: str
    vega_unit: str
    input_futures_price: float
    input_strike: float
    input_expiry_years: float
    risk_free_rate: float

    def __post_init__(self) -> None:
        if self.observation_time.tzinfo is None:
            raise ValueError("OBSERVATION_TIME_MUST_BE_TIMEZONE_AWARE")


@dataclass(frozen=True)
class ExposureSnapshot:
    symbol: str
    as_of: datetime
    calculation_version: str
    dataset_version: str
    net_gex: float | None
    net_dex: float | None
    gross_gex: float | None
    gross_dex: float | None
    oi_total: float | None
    oi_change_total: float | None
    iv: float | None
    gamma_flip: float | None
    call_wall: float | None
    put_wall: float | None
    expiry_scope: str
    sign_convention: str
    gamma_source: str


@dataclass(frozen=True)
class MarketState:
    symbol: str
    price: float | None
    as_of: datetime
    oi: float | None
    oi_change: float | None
    gex: float | None
    dex: float | None
    iv: float | None
    realized_vol: float | None
    gamma_flip: float | None
    call_wall: float | None
    put_wall: float | None
    positioning_regime: str
    volatility_regime: str
    data_quality: float
    data_age_seconds: float | None
    data_status: DataStatus
    dataset_version: str
    calculation_version: str
    sign_convention: str | None = None
    gamma_source: str | None = None
    assumptions: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None:
            raise ValueError("AS_OF_MUST_BE_TIMEZONE_AWARE")
        if not 0.0 <= self.data_quality <= 1.0:
            raise ValueError("DATA_QUALITY_OUT_OF_RANGE")
        if self.data_age_seconds is not None and self.data_age_seconds < 0:
            raise ValueError("DATA_AGE_MUST_BE_NON_NEGATIVE")
