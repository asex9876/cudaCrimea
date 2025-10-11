"""DAO for upserting events from ingestors."""

from __future__ import annotations

from datetime import date, time
from typing import Any, Mapping, Optional

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.services.quality import combined_quality
from app.db.models import Event


logger = structlog.get_logger(module="dao.events")


async def upsert_event(
    session: AsyncSession,
    *,
    title: str,
    date_: date,
    time_: Optional[time],
    city: Optional[str] = None,
    venue_name: str,
    address: Optional[str],
    lat: Optional[float],
    lon: Optional[float],
    price_min: Optional[int],
    price_max: Optional[int],
    category: str,
    source: str,
    source_url: str,
    quality_base: Optional[float] = None,
) -> Event:
    """Upsert event by (title, date, venue_name).

    Args:
        session: DB session.
        title: Event title.
        date_: Event date.
        time_: Optional time.
        venue_name: Venue name.
        address: Optional address.
        lat: Optional latitude.
        lon: Optional longitude.
        price_min: Optional minimal price.
        price_max: Optional maximal price.
        category: Event category string.
        source: Source system name.
        source_url: Source URL.
        quality_base: Optional quality indicator to combine with source weight.

    Returns:
        Event: ORM instance persisted.
    """

    stmt = select(Event).where(
        and_(Event.title == title, Event.date == date_, Event.venue_name == venue_name)
    )
    existing = (await session.execute(stmt)).scalars().first()

    quality_score = combined_quality(source, quality_base)

    if existing:
        existing.time = time_
        existing.city = city or existing.city
        existing.address = address or existing.address
        existing.lat = lat
        existing.lon = lon
        existing.price_min = price_min
        existing.price_max = price_max
        existing.category = category
        existing.source = source
        existing.source_url = source_url
        existing.quality_score = quality_score
        logger.info("event.update", title=title)
        return existing

    ev = Event(
        title=title,
        date=date_,
        time=time_,
        city=city,
        price_min=price_min,
        price_max=price_max,
        category=category,
        venue_name=venue_name,
        address=address or "",
        lat=lat,
        lon=lon,
        source=source,
        source_url=source_url,
        quality_score=quality_score,
    )
    session.add(ev)
    logger.info("event.insert", title=title)
    return ev

