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
    district: Optional[str] = None,
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
        district=district,
        source=source,
        source_url=source_url,
        quality_score=quality_score,
    )
    session.add(ev)
    logger.info("event.insert", title=title)
    return ev


async def find_events_nearby(
    session: AsyncSession,
    lat: float,
    lon: float,
    radius_km: float = 5.0,
    limit: int = 50,
) -> list[Event]:
    """Find events within a radius from coordinates using Haversine formula.

    Args:
        session: DB session.
        lat: Center latitude.
        lon: Center longitude.
        radius_km: Search radius in kilometers (default: 5 km).
        limit: Maximum number of events to return.

    Returns:
        List of events sorted by distance (closest first).
    """
    from app.core.services.geo import distance_km
    from datetime import datetime

    # First, get all events with coordinates from today onwards
    today = datetime.now().date()
    stmt = select(Event).where(
        and_(
            Event.lat.isnot(None),
            Event.lon.isnot(None),
            Event.date >= today,
        )
    )
    result = await session.execute(stmt)
    all_events = result.scalars().all()

    # Filter by distance and sort
    events_with_distance = []
    for event in all_events:
        if event.lat is not None and event.lon is not None:
            dist = distance_km(lat, lon, float(event.lat), float(event.lon))
            if dist <= radius_km:
                events_with_distance.append((dist, event))

    # Sort by distance and limit
    events_with_distance.sort(key=lambda x: x[0])
    nearby_events = [event for _, event in events_with_distance[:limit]]

    logger.info(
        "events.nearby_search",
        lat=lat,
        lon=lon,
        radius_km=radius_km,
        found=len(nearby_events),
    )

    return nearby_events

