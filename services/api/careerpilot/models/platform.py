"""Cross-cutting platform tables: notifications, consent, privacy requests, audit, tasks, AI usage, reports."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from careerpilot.db import Base, JSONType, TimestampMixin, UUIDPk


class Notification(UUIDPk, TimestampMixin, Base):
    __tablename__ = "notifications"
    # dedupe_key prevents repeated notifications for the same event.
    __table_args__ = (UniqueConstraint("user_id", "dedupe_key"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(300))
    dedupe_key: Mapped[str] = mapped_column(String(200))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    email_status: Mapped[str] = mapped_column(String(20), default="not_sent")  # not_sent|sent|failed|skipped


class NotificationPreference(UUIDPk, TimestampMixin, Base):
    __tablename__ = "notification_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    email_application_updates: Mapped[bool] = mapped_column(default=True)
    email_recommendations: Mapped[bool] = mapped_column(default=False)
    email_processing_updates: Mapped[bool] = mapped_column(default=True)


class ConsentRecord(UUIDPk, TimestampMixin, Base):
    """Append-only consent log; the latest record per (user, consent_type) is authoritative."""

    __tablename__ = "consent_records"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    consent_type: Mapped[str] = mapped_column(String(40))  # ai_processing|recommendation_tracking|...
    granted: Mapped[bool] = mapped_column()
    policy_version: Mapped[str] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(40), default="settings")


class DataDeletionRequest(UUIDPk, TimestampMixin, Base):
    __tablename__ = "data_deletion_requests"

    # Not a FK: the user row is anonymized but the request must remain auditable.
    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(String(20))  # requested|processing|completed|failed
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)


class AuditEvent(UUIDPk, TimestampMixin, Base):
    __tablename__ = "audit_events"

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    target_type: Mapped[str | None] = mapped_column(String(40))
    target_id: Mapped[str | None] = mapped_column(String(64))
    event_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    request_id: Mapped[str | None] = mapped_column(String(64))
    ip_prefix: Mapped[str | None] = mapped_column(String(64))


class BackgroundTask(UUIDPk, TimestampMixin, Base):
    __tablename__ = "background_tasks"

    name: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)  # queued|running|succeeded|failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(500))  # safe summary, no secrets/PII
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AIUsageRecord(UUIDPk, TimestampMixin, Base):
    __tablename__ = "ai_usage_records"

    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(100))
    operation: Mapped[str] = mapped_column(String(60))
    prompt_version: Mapped[str | None] = mapped_column(String(60))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    success: Mapped[bool] = mapped_column()
    error_code: Mapped[str | None] = mapped_column(String(60))


class Report(UUIDPk, TimestampMixin, Base):
    """Abuse/fraud reports about jobs, companies or users."""

    __tablename__ = "reports"

    reporter_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    target_type: Mapped[str] = mapped_column(String(20))  # job|company|user
    target_id: Mapped[uuid.UUID] = mapped_column(index=True)
    reason: Mapped[str] = mapped_column(String(40))  # fraud|discriminatory|misleading|abusive|other
    details: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)  # open|actioned|dismissed


class ModerationAction(UUIDPk, TimestampMixin, Base):
    __tablename__ = "moderation_actions"

    admin_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    report_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("reports.id", ondelete="SET NULL"))
    target_type: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[uuid.UUID] = mapped_column()
    action: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str | None] = mapped_column(Text)


Index("ix_audit_events_created", AuditEvent.created_at)
