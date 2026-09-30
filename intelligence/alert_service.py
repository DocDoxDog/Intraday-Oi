from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from intelligence.alert_policy import AlertGate


@dataclass(frozen=True)
class AlertDeliveryRecord:
    alert_id: str
    organization_id: str
    story_cluster_id: str
    channel: str
    destination: str
    provider_message_id: str | None
    version: int
    status: str
    updated_at: datetime


class AlertRepository(Protocol):
    def find_story(self, organization_id: str, story_cluster_id: str) -> AlertDeliveryRecord | None: ...
    def create(self, record: AlertDeliveryRecord) -> None: ...
    def update(self, record: AlertDeliveryRecord) -> None: ...


class AlertTransport(Protocol):
    def send(self, destination: str, text: str) -> str: ...
    def edit(self, destination: str, provider_message_id: str, text: str) -> None: ...


class CustomerAlertService:
    def __init__(self, repository: AlertRepository, transport: AlertTransport, gate: AlertGate | None = None):
        self.repository = repository
        self.transport = transport
        self.gate = gate or AlertGate()

    def publish(
        self,
        *,
        organization_id: str,
        story_cluster_id: str,
        destination: str,
        severity: str,
        text: str,
        alert_id: str,
    ) -> tuple[bool, str]:
        now = datetime.now(timezone.utc)
        existing = self.repository.find_story(organization_id, story_cluster_id)

        if existing and existing.provider_message_id:
            self.transport.edit(
                destination,
                existing.provider_message_id,
                text,
            )
            updated = AlertDeliveryRecord(
                alert_id=existing.alert_id,
                organization_id=organization_id,
                story_cluster_id=story_cluster_id,
                channel=existing.channel,
                destination=destination,
                provider_message_id=existing.provider_message_id,
                version=existing.version + 1,
                status="EDITED",
                updated_at=now,
            )
            self.repository.update(updated)
            return True, "EDITED"

        allowed, reason = self.gate.allow(
            severity=severity,
            story_cluster_id=story_cluster_id,
            now=now,
        )
        if not allowed:
            return False, reason

        provider_id = self.transport.send(destination, text)
        record = AlertDeliveryRecord(
            alert_id=alert_id,
            organization_id=organization_id,
            story_cluster_id=story_cluster_id,
            channel="TELEGRAM",
            destination=destination,
            provider_message_id=provider_id,
            version=1,
            status="SENT",
            updated_at=now,
        )
        self.repository.create(record)
        return True, "SENT"
