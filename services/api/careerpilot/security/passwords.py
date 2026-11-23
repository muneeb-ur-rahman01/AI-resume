"""Argon2id password hashing and password policy (NIST SP 800-63B style: length over composition)."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# argon2-cffi defaults follow RFC 9106 "low memory" recommendations (Argon2id, 64 MiB, t=3, p=4).
_hasher = PasswordHasher()

# A dummy hash to verify against when the account does not exist, so response time does not
# reveal whether an email is registered.
_DUMMY_HASH = _hasher.hash("timing-equalizer-not-a-real-password")

MIN_LENGTH = 12
MAX_LENGTH = 128
_COMMON = {
    "password1234",
    "123456789012",
    "qwertyuiop12",
    "passwordpassword",
    "letmein12345",
    "iloveyou1234",
    "administrator",
    "welcome12345",
    "changeme1234",
    "careerpilot123",
    "abc123456789",
    "000000000000",
}


def password_problems(password: str, *, email: str | None = None, name: str | None = None) -> list[str]:
    problems: list[str] = []
    if len(password) < MIN_LENGTH:
        problems.append(f"Password must be at least {MIN_LENGTH} characters.")
    if len(password) > MAX_LENGTH:
        problems.append(f"Password must be at most {MAX_LENGTH} characters.")
    lowered = password.lower()
    if lowered in _COMMON or len(set(password)) < 4:
        problems.append("Password is too common or too repetitive.")
    if email:
        local = email.split("@", 1)[0].lower()
        if len(local) >= 4 and local in lowered:
            problems.append("Password must not contain your email address.")
    if name and len(name) >= 4 and name.lower().replace(" ", "") in lowered.replace(" ", ""):
        problems.append("Password must not contain your name.")
    return problems


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)
