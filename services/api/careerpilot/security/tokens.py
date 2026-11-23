"""Opaque random tokens. Only SHA-256 digests are persisted; comparisons are constant-time."""

from __future__ import annotations

import hashlib
import hmac
import secrets


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def tokens_match(token: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_token(token), expected_hash)
