from datetime import datetime, timezone

from intelligence.alert_policy import AlertGate, AlertPolicy
from intelligence.alert_service import AlertDeliveryRecord, CustomerAlertService


class Repo:
    def __init__(self):
        self.records = {}
        self.created = []
        self.updated = []
    def find_story(self, organization_id, story_cluster_id):
        return self.records.get((organization_id, story_cluster_id))
    def create(self, record):
        self.records[(record.organization_id, record.story_cluster_id)] = record
        self.created.append(record)
    def update(self, record):
        self.records[(record.organization_id, record.story_cluster_id)] = record
        self.updated.append(record)


class Transport:
    def __init__(self):
        self.sent = []
        self.edited = []
    def send(self, destination, text):
        self.sent.append((destination, text))
        return f"msg-{len(self.sent)}"
    def edit(self, destination, provider_message_id, text):
        self.edited.append((destination, provider_message_id, text))


def test_alert_service_sends_once_then_edits_story():
    repo = Repo()
    transport = Transport()
    service = CustomerAlertService(
        repo,
        transport,
        AlertGate(AlertPolicy()),
    )
    ok, reason = service.publish(
        organization_id="org1",
        story_cluster_id="story1",
        destination="chat1",
        severity="CRITICAL",
        text="first",
        alert_id="a1",
    )
    assert (ok, reason) == (True, "SENT")
    assert transport.sent == [("chat1", "first")]

    ok, reason = service.publish(
        organization_id="org1",
        story_cluster_id="story1",
        destination="chat1",
        severity="CRITICAL",
        text="update",
        alert_id="a2",
    )
    assert (ok, reason) == (True, "EDITED")
    assert transport.edited == [("chat1", "msg-1", "update")]
    assert repo.updated[-1].version == 2


def test_alert_service_blocks_unlicensed_source():
    repo = Repo()
    transport = Transport()
    service = CustomerAlertService(repo, transport, AlertGate(AlertPolicy()))
    ok, reason = service.publish(
        organization_id="org1",
        story_cluster_id="story2",
        destination="chat1",
        severity="CRITICAL",
        text="unlicensed",
        alert_id="a2",
        source_rights_approved=False,
    )
    assert (ok, reason) == (False, "SOURCE_RIGHTS_NOT_APPROVED")
    assert transport.sent == []
