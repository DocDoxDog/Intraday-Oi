from __future__ import annotations

from datetime import date, datetime

from quant.contracts import OptionContract, OptionType, canonical_id
from quant.models import DataStatus, OIObservation


def observation_from_row(
    contract: OptionContract,
    row: dict,
    *,
    trade_date: date,
    observation_time: datetime,
    publication_time: datetime | None,
    availability_time: datetime | None,
    ingestion_time: datetime,
    calculation_time: datetime | None,
    dataset_version: str,
    source: str,
    data_status: DataStatus = DataStatus.VALID,
) -> OIObservation:
    if contract.resolution_status != "RESOLVED":
        raise ValueError("CANONICAL_CONTRACT_UNRESOLVED")

    option_type = contract.option_type
    if option_type not in {OptionType.CALL, OptionType.PUT}:
        raise ValueError("OPTION_TYPE_REQUIRED")

    oi = row.get("oi")
    if oi is None:
        oi = row.get("oiCall") if option_type == OptionType.CALL else row.get("oiPut")
    if oi is None:
        raise ValueError("OI_MISSING")

    oi_change = row.get("oi_change")
    if oi_change is None:
        oi_change = row.get("oiCallChange") if option_type == OptionType.CALL else row.get("oiPutChange")

    volume = row.get("volume")
    if volume is None:
        volume = row.get("volumeCall") if option_type == OptionType.CALL else row.get("volumePut")

    return OIObservation(
        observation_id=canonical_id(
            "oi-observation",
            contract.canonical_id,
            trade_date,
            observation_time.isoformat(),
            source,
            dataset_version,
        ),
        instrument_id=contract.instrument_id,
        expiration_id=contract.expiration_id,
        strike_id=contract.strike_id,
        trade_date=trade_date,
        observation_time=observation_time,
        publication_time=publication_time,
        availability_time=availability_time,
        ingestion_time=ingestion_time,
        calculation_time=calculation_time,
        option_type=option_type,
        oi=float(oi),
        oi_change=float(oi_change) if oi_change is not None else None,
        volume=float(volume) if volume is not None else None,
        source=source,
        dataset_version=dataset_version,
        data_status=data_status,
        timezone="UTC",
    )
