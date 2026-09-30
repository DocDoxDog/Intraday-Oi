from datetime import datetime, timezone, timedelta

from intelligence.customer.api_keys import hash_api_key, issue_api_key
from intelligence.customer.entitlements import Entitlement
from intelligence.customer.gateway import (
    ApiKeyRecord,
    InMemoryApiKeyStore,
    authorize_customer_api,
)


class Record:
    def __init__(self, organization_id, key_hash, revoked_at=None, expires_at=None):
        self.organization_id = organization_id
        self.key_hash = key_hash
        self.revoked_at = revoked_at
        self.expires_at = expires_at


def test_api_key_is_hashed_and_not_reversible():
    material = issue_api_key()
    assert material.plaintext != material.key_hash
    assert hash_api_key(material.plaintext) == material.key_hash


def test_customer_api_requires_entitlement():
    material = issue_api_key()
    record = Record("org-1", material.key_hash)
    store = InMemoryApiKeyStore([record])
    now = datetime.now(timezone.utc)
    decision = authorize_customer_api(
        material.plaintext,
        store=store,
        feature="gex_realtime",
        entitlements=(Entitlement("org-1", "gex_realtime", True, now - timedelta(minutes=1)),),
    )
    assert decision.allowed is True
    assert decision.organization_id == "org-1"


def test_customer_api_blocks_revoked_key():
    material = issue_api_key()
    record = Record("org-1", material.key_hash, revoked_at=datetime.now(timezone.utc))
    decision = authorize_customer_api(
        material.plaintext,
        store=InMemoryApiKeyStore([record]),
        feature="gex_realtime",
    )
    assert decision.allowed is False
    assert decision.reason == "API_KEY_REVOKED_OR_EXPIRED"


def test_customer_api_blocks_other_org_entitlement():
    material = issue_api_key()
    record = Record("org-1", material.key_hash)
    now = datetime.now(timezone.utc)
    decision = authorize_customer_api(
        material.plaintext,
        store=InMemoryApiKeyStore([record]),
        feature="gex_realtime",
        entitlements=(Entitlement("org-2", "gex_realtime", True, now - timedelta(minutes=1)),),
    )
    assert decision.allowed is False
    assert decision.reason == "ENTITLEMENT_NOT_FOUND"
