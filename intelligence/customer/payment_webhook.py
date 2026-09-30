from __future__ import annotations

import hashlib
import hmac

from dataclasses import dataclass

@dataclass(frozen=True)
class WebhookEnvelope:
    provider: str
    provider_event_id: str
    event_type: str
    signature_valid: bool
    payload_hash: str

def payload_hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()

def verify_hmac_sha256(payload: bytes, signature: str, secret: str) -> bool:
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)