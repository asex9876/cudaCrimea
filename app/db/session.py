"""Async SQLAlchemy engine and session factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Get or create the global async engine.

    Returns:
        AsyncEngine: SQLAlchemy async engine instance.
    """

    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(str(settings.database_url), pool_pre_ping=True)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Get or create the global async sessionmaker.

    Returns:
        async_sessionmaker[AsyncSession]: Session factory.
    """

    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _sessionmaker


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an `AsyncSession`.

    Yields:
        AsyncSession: Database session.
    """

    async_session = get_sessionmaker()
    async with async_session() as session:  # type: ignore[call-arg]
        yield session

