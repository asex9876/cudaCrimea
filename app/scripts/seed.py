"""Seed reference data (dev helper)."""

from __future__ import annotations

import asyncio

import structlog
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import setup_logging
from app.db.models.tables import Place
from app.db.session import get_sessionmaker


logger = structlog.get_logger(module="scripts.seed")


async def seed() -> None:
    ss = get_sessionmaker()
    async with ss() as session:  # type: ignore[call-arg]
        await _seed_places(session)
        await session.commit()
    logger.info("db.seed.completed")


async def _seed_places(session: AsyncSession) -> None:
    rows = [
        {
            "name": "Кофейня Морская",
            "category": "coffee",
            "address": "Севастополь, центр",
            "lat": 44.430,
            "lon": 34.132,
            "phone": None,
            "hours": None,
            "rating": 4.6,
            "price_level": 2,
            "source": "seed",
            "external_id": "seed:sev:coffee1",
            "image_url": None,
        },
        {
            "name": "Столовая Синяя",
            "category": "restaurant",
            "address": "Ялта, набережная",
            "lat": 44.498,
            "lon": 34.166,
            "phone": None,
            "hours": None,
            "rating": 4.2,
            "price_level": 1,
            "source": "seed",
            "external_id": "seed:yal:rest1",
            "image_url": None,
        },
        {
            "name": "Бургерная Центр",
            "category": "restaurant",
            "address": "Севастополь, пл. Нахимова",
            "lat": 44.6175,
            "lon": 33.5260,
            "phone": None,
            "hours": None,
            "rating": 4.3,
            "price_level": 2,
            "source": "seed",
            "external_id": "seed:sev:rest2",
            "image_url": None,
        },
    ]
    await session.execute(insert(Place).values(rows))


def main() -> None:
    setup_logging()
    asyncio.run(seed())


if __name__ == "__main__":
    main()
