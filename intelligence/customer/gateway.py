from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from intelligence.customer.api_keys import verify_api_key
from intelligence.customer.entitlements import Entitlement, check_entitlement


class ApiKeyRecord(Protocol):
    organization_id: str
    key_hash: str
    revoked_at: datetime | None
    expires_at: datetime | None


class ApiKeyStore(Protocol):
    def get_by_hash(self, key_hash: str) -> ApiKeyRecord | None: ...


@dataclass(frozen=True)
class CustomerApiDecision:
    allowed: bool
    organization_id: str | None
    reason: str


class InMemoryApiKeyStore:
    def __init__(self, records=()):
        self.records = list(records)

    def get_by_hash(self, key_hash: str):
        return next((x for x in self.records if x.key_hash == key_hash), None)


def authorize_customer_api(
    plaintext_api_key: str,
    *,
    store: ApiKeyStore,
    feature: str,
    entitlements: tuple[Entitlement, ...] = (),
) -> CustomerApiDecision:
    if not plaintext_api_key:
        return CustomerApiDecision(False, None, "API_KEY_REQUIRED")
    record = store.get_by_hash(__import__("hashlib").sha256(plaintext_api_key.encode()).hexdigest())
    if record is None:
        return CustomerApiDecision(False, None, "API_KEY_INVALID")
    if not verify_api_key(
        plaintext_api_key,
        record.key_hash,
        revoked_at=record.revoked_at,
        expires_at=record.expires_at,
    ):
        return CustomerApiDecision(False, record.organization_id, "API_KEY_REVOKED_OR_EXPIRED")
    entitlement = check_entitlement(
        entitlements,
        organization_id=record.organization_id,
        feature=feature,
        now=datetime.now(timezone.utc),
    )
    if not entitlement.allowed:
        return CustomerApiDecision(False, record.organization_id, entitlement.reason)
    return CustomerApiDecision(True, record.organization_id, "AUTHORIZED")


from collections import defaultdict, deque


class CustomerApiRateLimiter:
    """Per-organization fixed-window limiter.

    This is a single-process guard. Multi-instance deployment must use a shared
    limiter/store rather than relying on this in-memory state.
    """

    def __init__(self, limit: int = 120, window_seconds: int = 60):
        self.limit = limit
        self.window_seconds = window_seconds
        self._events = defaultdict(deque)

    def allow(self, organization_id: str, *, now: float | None = None) -> bool:
        import time
        current = time.time() if now is None else now
        events = self._events[organization_id]
        cutoff = current - self.window_seconds
        while events and events[0] <= cutoff:
            events.popleft()
        if len(events) >= self.limit:
            return False
        events.append(current)
        return True
