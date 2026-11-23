"""Database engine, session factory and portable column types.

PostgreSQL + pgvector is the supported production database. SQLite is supported only
for fast unit/API tests; the Vector type degrades to JSON there and similarity search
falls back to an in-Python implementation (see matching.retrieval).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, MetaData, String, create_engine, event, func
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Dialect, Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import TypeDecorator, Uuid

from careerpilot.config import get_settings

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# JSONB on PostgreSQL, JSON elsewhere.
JSONType = JSON().with_variant(postgresql.JSONB(), "postgresql")


class Vector(TypeDecorator[list[float]]):
    """pgvector `vector` on PostgreSQL (dimension-less so several embedding models can coexist),
    JSON array elsewhere."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> Any:
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector as PgVector

            return dialect.type_descriptor(PgVector())
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value: list[float] | None, dialect: Dialect) -> Any:
        if value is None:
            return None
        return [float(v) for v in value]

    def process_result_value(self, value: Any, dialect: Dialect) -> list[float] | None:
        if value is None:
            return None
        return [float(v) for v in value]


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {uuid.UUID: Uuid(), dict[str, Any]: JSONType, str: String()}


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, server_default=func.now(), nullable=False
    )


class UUIDPk:
    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def make_engine(url: str) -> Engine:
    settings = get_settings()
    if url.startswith("sqlite"):
        engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool if ":memory:" in url else None,
        )

        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn: Any, _record: Any) -> None:  # enforce ON DELETE CASCADE like PostgreSQL
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine
    return create_engine(
        url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        future=True,
    )


def configure_engine(url: str | None = None) -> Engine:
    global _engine, _SessionLocal
    _engine = make_engine(url or get_settings().database_url)
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, autoflush=False)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        configure_engine()
    assert _engine is not None
    return _engine


def session_factory() -> sessionmaker[Session]:
    if _SessionLocal is None:
        configure_engine()
    assert _SessionLocal is not None
    return _SessionLocal


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request; rolled back on error."""
    db = session_factory()()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
