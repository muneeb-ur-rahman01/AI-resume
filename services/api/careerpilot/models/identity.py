"""Identity: users, roles, credentials, sessions, single-use tokens."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from careerpilot.db import Base, TimestampMixin, UUIDPk


class Role(enum.StrEnum):
    candidate = "candidate"
    employer = "employer"
    admin = "admin"


class UserStatus(enum.StrEnum):
    active = "active"
    suspended = "suspended"
    deleted = "deleted"


class User(UUIDPk, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, native_enum=False, length=20), default=UserStatus.active
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mfa_enabled: Mapped[bool] = mapped_column(default=False)

    roles: Mapped[list[UserRole]] = relationship(back_populates="user", cascade="all, delete-orphan", lazy="selectin")
    credential: Mapped[UserCredential | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )

    @property
    def role_names(self) -> set[str]:
        return {r.role.value for r in self.roles}

    def has_role(self, role: Role) -> bool:
        return role.value in self.role_names


class UserRole(UUIDPk, TimestampMixin, Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[Role] = mapped_column(Enum(Role, native_enum=False, length=20))
    user: Mapped[User] = relationship(back_populates="roles")


class UserCredential(UUIDPk, TimestampMixin, Base):
    """Password hash (Argon2id). Kept apart from `users` so profile queries never load hashes."""

    __tablename__ = "user_credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user: Mapped[User] = relationship(back_populates="credential")


class UserSession(UUIDPk, TimestampMixin, Base):
    """Server-side session. Only SHA-256 hashes of the session and CSRF tokens are stored."""

    __tablename__ = "user_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    ip_prefix: Mapped[str | None] = mapped_column(String(64))  # truncated IP, not full address


class EmailVerificationToken(UUIDPk, TimestampMixin, Base):
    __tablename__ = "email_verification_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    email: Mapped[str] = mapped_column(String(320))  # the address being verified
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PasswordResetToken(UUIDPk, TimestampMixin, Base):
    __tablename__ = "password_reset_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


Index("ix_user_sessions_active", UserSession.user_id, UserSession.revoked_at)
