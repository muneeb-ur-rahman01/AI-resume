"""Embeddings, recommendations, recommendation feedback events, saved jobs."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from careerpilot.db import Base, JSONType, TimestampMixin, UUIDPk, Vector


class Embedding(UUIDPk, TimestampMixin, Base):
    """Versioned embedding for a candidate profile or job. Re-generated when content or model changes."""

    __tablename__ = "embeddings"
    __table_args__ = (UniqueConstraint("owner_type", "owner_id", "model"),)

    owner_type: Mapped[str] = mapped_column(String(20))  # candidate|job
    owner_id: Mapped[uuid.UUID] = mapped_column(index=True)
    model: Mapped[str] = mapped_column(String(100))
    dimensions: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    vector: Mapped[list[float]] = mapped_column(Vector())


class JobRecommendation(UUIDPk, TimestampMixin, Base):
    __tablename__ = "job_recommendations"
    __table_args__ = (UniqueConstraint("candidate_user_id", "job_id"),)

    candidate_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    relevance_score: Mapped[float] = mapped_column()
    eligibility: Mapped[str] = mapped_column(String(30))
    components: Mapped[dict[str, Any]] = mapped_column(JSONType)
    explanation: Mapped[dict[str, Any]] = mapped_column(JSONType)
    algorithm_version: Mapped[str] = mapped_column(String(30))


class RecommendationEvent(UUIDPk, TimestampMixin, Base):
    __tablename__ = "recommendation_events"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(20))  # impression|click|save|dismiss|apply|...
    algorithm_version: Mapped[str | None] = mapped_column(String(30))
    relevance_score: Mapped[float | None] = mapped_column()


class SavedJob(UUIDPk, TimestampMixin, Base):
    __tablename__ = "saved_jobs"
    __table_args__ = (UniqueConstraint("user_id", "job_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))


Index("ix_embeddings_owner", Embedding.owner_type, Embedding.model)
