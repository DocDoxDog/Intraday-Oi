from datetime import datetime, timezone, timedelta

from intelligence.customer.api_keys import issue_api_key
from intelligence.customer.supabase_access import SupabaseCustomerAccessStore


class Query:
    def __init__(self, rows):
        self.rows = rows
        self.filters = {}

    def select(self, *_):
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def limit(self, *_):
        return self

    def execute(self):
        if "key_hash" in self.filters:
            return type("R", (), {"data": self.rows["keys"]})()
        if "feature" in self.filters:
            return type("R", (), {"data": self.rows["entitlements"]})()
        return type("R", (), {"data": self.rows["markets"]})()


class Schema:
    def __init__(self, rows):
        self.rows = rows

    def table(self, name):
        return Query(self.rows)


class Client:
    def __init__(self, rows):
        self.rows = rows

    def schema(self, name):
        assert name == "commercial"
        return Schema(self.rows)


def test_customer_store_authorizes_feature_and_market():
    material = issue_api_key()
    rows = {
        "keys": [{
            "id": "k1",
            "organization_id": "org-1",
            "key_hash": material.key_hash,
            "revoked_at": None,
            "expires_at": None,
        }],
        "entitlements": [{
            "enabled": True,
            "effective_from": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
            "effective_to": None,
        }],
        "markets": [{"enabled": True, "effective_from": None, "effective_to": None}],
    }
    store = SupabaseCustomerAccessStore(client=Client(rows))
    assert store.authorize(material.plaintext, feature="gex", symbol="GC")[0] is True
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    rows["entitlements"][0]["effective_from"] = future
    assert store.authorize(material.plaintext, feature="gex", symbol="GC")[2] == "ENTITLEMENT_NOT_YET_ACTIVE"


def test_customer_store_rejects_missing_key():
    material = issue_api_key()
    rows = {"keys": [], "entitlements": [], "markets": []}
    store = SupabaseCustomerAccessStore(client=Client(rows))
    ok, org, reason = store.authorize(material.plaintext, feature="gex")
    assert (ok, org, reason) == (False, None, "API_KEY_INVALID")
