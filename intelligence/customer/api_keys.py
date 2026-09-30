from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class ApiKeyMaterial:
    plaintext: str
    key_prefix: str
    key_hash: str


def hash_api_key(plaintext: str) -> str:
    if not plaintext:
        raise ValueError("API_KEY_REQUIRED")
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def issue_api_key(prefix: str = "ami") -> ApiKeyMaterial:
    token = f"{prefix}_{secrets.token_urlsafe(32)}"
    return ApiKeyMaterial(
        plaintext=token,
        key_prefix=token[: min(len(token), len(prefix) + 5)],
        key_hash=hash_api_key(token),
    )


def verify_api_key(plaintext: str, stored_hash: str, *, revoked_at: datetime | None = None, expires_at: datetime | None = None) -> bool:
    if revoked_at is not None:
        return False
    if expires_at is not None:
        now = datetime.now(timezone.utc)
        if expires_at.tzinfo is None:
            raise ValueError("EXPIRY_MUST_BE_TIMEZONE_AWARE")
        if now >= expires_at:
            return False
    return secrets.compare_digest(hash_api_key(plaintext), stored_hash)
