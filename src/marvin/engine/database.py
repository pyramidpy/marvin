"""Database management for persistence.

This module provides utilities for managing database sessions and migrations.
"""

import uuid
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime
from typing import Any, Optional

from pydantic import TypeAdapter
from sqlalchemy import JSON, ForeignKey, String, create_engine, inspect
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
)

from marvin.settings import settings

from .llm import Message

message_adapter: TypeAdapter[Message] = TypeAdapter(Message)

# Module-level cache for engines
_engine_cache = {}
_async_engine_cache = {}


def get_engine():
    """Get the SQLAlchemy engine for sync operations."""
    if "default" not in _engine_cache:
        _engine_cache["default"] = create_engine(
            f"sqlite:///{settings.database_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )
    return _engine_cache["default"]


def get_async_engine():
    """Get the SQLAlchemy engine for async operations."""
    if "default" not in _async_engine_cache:
        _async_engine_cache["default"] = create_async_engine(
            f"sqlite+aiosqlite:///{settings.database_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )
    return _async_engine_cache["default"]


def set_engine(engine):
    """Set the SQLAlchemy engine for sync operations."""
    _engine_cache["default"] = engine


def set_async_engine(engine):
    """Set the SQLAlchemy engine for async operations."""
    _async_engine_cache["default"] = engine


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class DBThread(Base):
    __tablename__ = "threads"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    parent_thread_id: Mapped[str | None] = mapped_column(ForeignKey("threads.id"))
    created_at: Mapped[datetime] = mapped_column(default=utc_now)

    messages: Mapped[list["DBMessage"]] = relationship(back_populates="thread")

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        parent_thread_id: str | None = None,
    ) -> "DBThread":
        thread = cls(id=str(uuid.uuid4()), parent_thread_id=parent_thread_id)
        session.add(thread)
        await session.commit()
        await session.refresh(thread)
        return thread


class DBMessage(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    thread_id: Mapped[str] = mapped_column(ForeignKey("threads.id"), index=True)
    llm_call_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("llm_calls.id"),
        default=None,
    )
    message: Mapped[dict[str, Any]] = mapped_column(JSON)
    timestamp: Mapped[datetime] = mapped_column(default=utc_now)

    thread: Mapped[DBThread] = relationship(back_populates="messages")
    llm_call: Mapped[Optional["DBLLMCall"]] = relationship(back_populates="messages")

    @classmethod
    def from_message(
        cls,
        thread_id: str,
        message: Message,
        llm_call_id: uuid.UUID | None = None,
    ) -> "DBMessage":
        return cls(
            thread_id=thread_id,
            message=message_adapter.dump_python(message, mode="json"),
            llm_call_id=llm_call_id,
        )


class DBLLMCall(Base):
    __tablename__ = "llm_calls"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    thread_id: Mapped[str] = mapped_column(ForeignKey("threads.id"), index=True)
    model: Mapped[str] = mapped_column(String, index=True)
    prompt: Mapped[dict[str, Any]] = mapped_column(JSON)
    cost: Mapped[dict[str, Any]] = mapped_column(JSON)
    timestamp: Mapped[datetime] = mapped_column(default=utc_now)

    messages: Mapped[list[DBMessage]] = relationship(back_populates="llm_call")


def ensure_tables_exist():
    """Initialize database tables if they don't exist yet."""
    inspector = inspect(get_engine())
    if not inspector.get_table_names():
        Base.metadata.create_all(get_engine())


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Get a database session."""
    session = Session(get_engine())
    try:
        yield session
    finally:
        session.close()


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Get an async database session."""
    session = AsyncSession(get_async_engine())
    try:
        yield session
    finally:
        await session.close()


def create_db_and_tables(*, force: bool = False):
    """Create all database tables.

    Args:
        force: If True, drops all existing tables before creating new ones.

    """
    if force:
        Base.metadata.drop_all(get_engine())
    Base.metadata.create_all(get_engine())
