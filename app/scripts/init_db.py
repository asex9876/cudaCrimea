"""Initialize the database schema (dev helper).

For production use Alembic migrations instead.
"""

from __future__ import annotations

import asyncio

import structlog
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.logging import setup_logging
from app.db.models.base import Base
from app.db.session import get_engine


logger = structlog.get_logger(module="scripts.init_db")


async def init_db() -> None:
    """Create all tables using SQLAlchemy metadata."""

    engine: AsyncEngine = get_engine()
    async with engine.begin() as conn:  # type: ignore[call-arg]
        await conn.run_sync(Base.metadata.create_all)
    logger.info("db.initialized")


def main() -> None:
    setup_logging()
    asyncio.run(init_db())


if __name__ == "__main__":
    main()

