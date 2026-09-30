from datetime import datetime, timezone, timedelta

from intelligence.customer.payment_webhook import payload_hash, verify_hmac_sha256
from intelligence.customer.subscription import SubscriptionState, features_for_subscription


def test_subscription_features_depend_on_active_status():
    state = SubscriptionState("org1", "PRO", "ACTIVE", None, False)
    assert "gex" in features_for_subscription(state)
    canceled = SubscriptionState("org1", "PRO", "CANCELED", None, False)
    assert features_for_subscription(canceled) == frozenset()


def test_webhook_hmac_and_payload_hash():
    payload = b"event"
    import hmac, hashlib
    signature = hmac.new(b"secret", payload, hashlib.sha256).hexdigest()
    assert verify_hmac_sha256(payload, signature, "secret")
    assert not verify_hmac_sha256(payload, signature, "wrong")
    assert len(payload_hash(payload)) == 64

def test_subscription_ends_at_period_end():
    state = SubscriptionState(
        "org1", "PRO", "ACTIVE",
        datetime(2026, 10, 1, tzinfo=timezone.utc), False,
    )
    assert not features_for_subscription(state, datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc))
