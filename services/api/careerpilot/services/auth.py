"""Registration, email verification, login/session management and password reset."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from careerpilot.config import get_settings
from careerpilot.db import utcnow
from careerpilot.errors import AppError, Unauthorized, ValidationFailed
from careerpilot.infra.email import OutgoingEmail, get_email_provider
from careerpilot.models import (
    CandidatePreferences,
    CandidateProfile,
    EmailVerificationToken,
    PasswordResetToken,
    Role,
    User,
    UserCredential,
    UserRole,
    UserSession,
    UserStatus,
)
from careerpilot.security import rate_limit as rl
from careerpilot.security.passwords import hash_password, needs_rehash, password_problems, verify_password
from careerpilot.security.tokens import hash_token, new_token
from careerpilot.services.audit import audit
from careerpilot.services.consent import record_consent


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _send_verification(db: Session, user: User) -> None:
    s = get_settings()
    token = new_token()
    db.add(
        EmailVerificationToken(
            user_id=user.id,
            token_hash=hash_token(token),
            email=user.email,
            expires_at=utcnow() + timedelta(minutes=s.email_verification_ttl_minutes),
        )
    )
    link = f"{s.frontend_url}/verify-email?token={token}"
    get_email_provider().send(
        OutgoingEmail(
            to=user.email,
            subject=f"Verify your {s.app_name} email address",
            text=(
                f"Hi {user.full_name},\n\nConfirm your email address by opening this link:\n{link}\n\n"
                f"The link expires in {s.email_verification_ttl_minutes // 60} hours and can be used once.\n"
                "If you did not create an account, you can ignore this message."
            ),
        )
    )


def register(
    db: Session, *, email: str, password: str, full_name: str, role: Role, ai_processing_consent: bool
) -> None:
    """Create an account. The response to the caller is identical whether or not the email already exists
    (account enumeration protection); an existing owner receives a notice email instead."""
    if role not in (Role.candidate, Role.employer):
        raise ValidationFailed("Invalid role.")
    email = normalize_email(email)
    problems = password_problems(password, email=email, name=full_name)
    if problems:
        raise ValidationFailed("Password does not meet the policy.", details={"password": problems})

    existing = db.scalar(select(User).where(User.email == email))
    if existing is not None:
        s = get_settings()
        get_email_provider().send(
            OutgoingEmail(
                to=email,
                subject=f"{s.app_name} sign-up attempt",
                text=(
                    "Someone tried to create an account with this email address. If this was you, sign in or "
                    f"reset your password at {s.frontend_url}/forgot-password."
                ),
            )
        )
        return

    user = User(email=email, full_name=full_name.strip())
    user.roles.append(UserRole(role=role))
    user.credential = UserCredential(password_hash=hash_password(password), password_changed_at=utcnow())
    db.add(user)
    try:
        db.flush()
    except IntegrityError:  # concurrent registration with the same email
        db.rollback()
        return
    if role == Role.candidate:
        profile = CandidateProfile(user_id=user.id)
        profile.preferences = CandidatePreferences()
        db.add(profile)
        record_consent(db, user.id, "ai_processing", ai_processing_consent, source="registration")
    audit(db, "user.registered", actor_id=user.id, target_type="user", target_id=user.id, metadata={"role": role.value})
    _send_verification(db, user)
    db.commit()


def verify_email(db: Session, token: str) -> None:
    record = db.scalar(select(EmailVerificationToken).where(EmailVerificationToken.token_hash == hash_token(token)))
    now = utcnow()
    if record is None or record.consumed_at is not None or _aware(record.expires_at) < now:
        raise AppError("This verification link is invalid or has expired.", code="invalid_token")
    user = db.get(User, record.user_id)
    if user is None or user.email != record.email:
        raise AppError("This verification link is invalid or has expired.", code="invalid_token")
    # Atomic single-use consumption: only one concurrent request can flip consumed_at.
    result = db.execute(
        update(EmailVerificationToken)
        .where(EmailVerificationToken.id == record.id, EmailVerificationToken.consumed_at.is_(None))
        .values(consumed_at=now)
    )
    if result.rowcount != 1:  # type: ignore[attr-defined]
        raise AppError("This verification link is invalid or has expired.", code="invalid_token")
    user.email_verified_at = user.email_verified_at or now
    audit(db, "user.email_verified", actor_id=user.id, target_type="user", target_id=user.id)
    db.commit()


def resend_verification(db: Session, email: str) -> None:
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    if user is not None and user.email_verified_at is None and user.status == UserStatus.active:
        _send_verification(db, user)
        db.commit()


@dataclass
class IssuedSession:
    token: str
    csrf_token: str
    session: UserSession


def _aware(dt: datetime) -> datetime:
    """SQLite returns naive datetimes; treat them as UTC."""
    from datetime import UTC

    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=UTC)


def issue_session(db: Session, user: User, *, user_agent: str | None, ip_prefix: str | None) -> IssuedSession:
    s = get_settings()
    token, csrf = new_token(), new_token()
    now = utcnow()
    session = UserSession(
        user_id=user.id,
        token_hash=hash_token(token),
        csrf_hash=hash_token(csrf),
        expires_at=now + timedelta(hours=s.session_ttl_hours),
        last_seen_at=now,
        user_agent=(user_agent or "")[:300] or None,
        ip_prefix=ip_prefix,
    )
    db.add(session)
    return IssuedSession(token, csrf, session)


def login(db: Session, *, email: str, password: str, user_agent: str | None, ip_prefix: str | None) -> IssuedSession:
    s = get_settings()
    email = normalize_email(email)
    limiter = rl.get_rate_limiter()
    if limiter.count(rl.LOGIN_ACCOUNT, email) >= s.login_max_failures:
        raise AppError(
            "Too many failed attempts. Try again later or reset your password.", code="account_locked", status_code=429
        )
    user = db.scalar(select(User).where(User.email == email))
    cred = db.scalar(select(UserCredential).where(UserCredential.user_id == user.id)) if user else None
    # verify_password always runs (against a dummy hash when unknown) to equalize timing.
    ok = verify_password(cred.password_hash if cred else None, password)
    if not ok or user is None or cred is None:
        limiter.increment(rl.Limit(rl.LOGIN_ACCOUNT.name, s.login_max_failures, s.login_lockout_minutes * 60), email)
        if user is not None:
            audit(db, "auth.login_failed", actor_id=None, target_type="user", target_id=user.id, ip_prefix=ip_prefix)
            db.commit()
        raise Unauthorized("Invalid email or password.", code="invalid_credentials")
    if user.status != UserStatus.active:
        raise AppError("This account is not active. Contact support.", code="account_inactive", status_code=403)
    if user.email_verified_at is None:
        raise AppError(
            "Please verify your email address before signing in.", code="email_not_verified", status_code=403
        )
    limiter.reset(rl.LOGIN_ACCOUNT, email)
    if needs_rehash(cred.password_hash):
        cred.password_hash = hash_password(password)
    user.last_login_at = utcnow()
    issued = issue_session(db, user, user_agent=user_agent, ip_prefix=ip_prefix)
    audit(db, "auth.login", actor_id=user.id, target_type="user", target_id=user.id, ip_prefix=ip_prefix)
    db.commit()
    return issued


def resolve_session(db: Session, token: str) -> tuple[User, UserSession] | None:
    s = get_settings()
    session = db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(token)))
    now = utcnow()
    if session is None or session.revoked_at is not None or _aware(session.expires_at) < now:
        return None
    if _aware(session.last_seen_at) < now - timedelta(hours=s.session_idle_timeout_hours):
        session.revoked_at = now
        db.commit()
        return None
    user = db.get(User, session.user_id)
    if user is None or user.status != UserStatus.active:
        return None
    if _aware(session.last_seen_at) < now - timedelta(minutes=5):  # throttle writes
        session.last_seen_at = now
        db.commit()
    return user, session


def revoke_session(db: Session, session: UserSession) -> None:
    session.revoked_at = utcnow()
    db.commit()


def revoke_all_sessions(db: Session, user_id: uuid.UUID, *, except_id: uuid.UUID | None = None) -> int:
    stmt = update(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
    if except_id:
        stmt = stmt.where(UserSession.id != except_id)
    result = db.execute(stmt.values(revoked_at=utcnow()))
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


def request_password_reset(db: Session, email: str) -> None:
    s = get_settings()
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    if user is None or user.status != UserStatus.active:
        return  # identical response either way
    db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.consumed_at.is_(None))
        .values(consumed_at=utcnow())
    )  # invalidate older outstanding tokens
    token = new_token()
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=utcnow() + timedelta(minutes=s.password_reset_ttl_minutes),
        )
    )
    get_email_provider().send(
        OutgoingEmail(
            to=user.email,
            subject=f"Reset your {s.app_name} password",
            text=(
                f"Use this link to choose a new password:\n{s.frontend_url}/reset-password?token={token}\n\n"
                f"It expires in {s.password_reset_ttl_minutes} minutes and works once. If you did not request "
                "this, ignore this email; your password is unchanged."
            ),
        )
    )
    audit(db, "auth.password_reset_requested", actor_id=None, target_type="user", target_id=user.id)
    db.commit()


def reset_password(db: Session, token: str, new_password: str) -> None:
    record = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(token)))
    now = utcnow()
    if record is None or record.consumed_at is not None or _aware(record.expires_at) < now:
        raise AppError("This reset link is invalid or has expired.", code="invalid_token")
    user = db.get(User, record.user_id)
    if user is None:
        raise AppError("This reset link is invalid or has expired.", code="invalid_token")
    problems = password_problems(new_password, email=user.email, name=user.full_name)
    if problems:
        raise ValidationFailed("Password does not meet the policy.", details={"password": problems})
    result = db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.id == record.id, PasswordResetToken.consumed_at.is_(None))
        .values(consumed_at=now)
    )
    if result.rowcount != 1:  # type: ignore[attr-defined]
        raise AppError("This reset link is invalid or has expired.", code="invalid_token")
    cred = db.scalar(select(UserCredential).where(UserCredential.user_id == user.id))
    assert cred is not None
    cred.password_hash = hash_password(new_password)
    cred.password_changed_at = now
    # Completing a reset through the emailed link proves mailbox control.
    user.email_verified_at = user.email_verified_at or now
    revoke_all_sessions(db, user.id)
    audit(db, "auth.password_reset_completed", actor_id=user.id, target_type="user", target_id=user.id)
    get_email_provider().send(
        OutgoingEmail(
            to=user.email,
            subject="Your password was changed",
            text="Your password was just changed and all sessions were signed out. If this was not you, "
            "reset your password immediately and contact support.",
        )
    )
    db.commit()


def reauthenticate(db: Session, user: User, password: str) -> None:
    cred = db.scalar(select(UserCredential).where(UserCredential.user_id == user.id))
    rl.get_rate_limiter().hit(rl.SENSITIVE, str(user.id))
    if cred is None or not verify_password(cred.password_hash, password):
        raise Unauthorized("Password is incorrect.", code="reauthentication_failed")


def change_password(db: Session, user: User, session: UserSession, current: str, new: str) -> None:
    reauthenticate(db, user, current)
    problems = password_problems(new, email=user.email, name=user.full_name)
    if problems:
        raise ValidationFailed("Password does not meet the policy.", details={"password": problems})
    cred = db.scalar(select(UserCredential).where(UserCredential.user_id == user.id))
    assert cred is not None
    cred.password_hash = hash_password(new)
    cred.password_changed_at = utcnow()
    revoke_all_sessions(db, user.id, except_id=session.id)
    audit(db, "auth.password_changed", actor_id=user.id, target_type="user", target_id=user.id)
    get_email_provider().send(
        OutgoingEmail(
            to=user.email,
            subject="Your password was changed",
            text="Your password was changed. Other sessions were signed out.",
        )
    )
    db.commit()
