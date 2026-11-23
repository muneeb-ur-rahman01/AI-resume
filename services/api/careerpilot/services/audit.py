"""Audit logging for security-relevant and administrative actions. Never store secrets in metadata."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from careerpilot.logging_config import redact, request_id_var
from careerpilot.models import AuditEvent


def audit(
    db: Session,
    action: str,
    *,
    actor_id: uuid.UUID | None,
    target_type: str | None = None,
    target_id: uuid.UUID | str | None = None,
    metadata: dict[str, Any] | None = None,
    ip_prefix: str | None = None,
) -> None:
    db.add(
        AuditEvent(
            actor_user_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id else None,
            event_metadata=redact(metadata or {}),
            request_id=request_id_var.get(),
            ip_prefix=ip_prefix,
        )
    )
