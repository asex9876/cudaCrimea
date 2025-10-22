"""DAO for upserting events from ingestors."""

from __future__ import annotations

from datetime import date, time, timedelta
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


async def find_similar_events(
    session: AsyncSession,
    query_embedding: list[float],
    threshold: float = 0.85,
    limit: int = 10,
    exclude_event_id: Optional[str] = None,
) -> list[tuple[Event, float]]:
    """Find similar events using cosine similarity of embeddings.

    Args:
        session: DB session.
        query_embedding: Query event embedding vector (1536 dimensions).
        threshold: Minimum similarity score (0-1, default 0.85).
        limit: Maximum number of results (default 10).
        exclude_event_id: Optional event ID to exclude from results (for self-comparison).

    Returns:
        List of (event, similarity_score) tuples sorted by similarity (descending).
    """
    from app.core.services.embedding import get_embedding_service
    from datetime import datetime
    from uuid import UUID

    embedding_service = get_embedding_service()

    # Get all events with embeddings from today onwards
    today = datetime.now().date()
    stmt = select(Event).where(
        and_(
            Event.embedding.isnot(None),
            Event.date >= today - timedelta(days=7),  # Include last week to catch duplicates
        )
    )
    result = await session.execute(stmt)
    all_events = result.scalars().all()

    # Calculate similarities
    similarities: list[tuple[Event, float]] = []
    for event in all_events:
        # Skip excluded event
        if exclude_event_id and str(event.id) == str(exclude_event_id):
            continue

        if event.embedding:
            try:
                similarity = embedding_service.cosine_similarity(
                    query_embedding,
                    event.embedding,
                )
                if similarity >= threshold:
                    similarities.append((event, similarity))
            except Exception as e:
                logger.warning(
                    "events.similarity_calculation_failed",
                    event_id=str(event.id),
                    error=str(e),
                )

    # Sort by similarity descending and limit
    similarities.sort(key=lambda x: x[1], reverse=True)
    results = similarities[:limit]

    logger.info(
        "events.similar_search",
        threshold=threshold,
        candidates=len(all_events),
        found=len(results),
    )

    return results


async def generate_and_save_embedding(
    session: AsyncSession,
    event: Event,
) -> bool:
    """Generate and save embedding for an event.

    Args:
        session: DB session.
        event: Event to generate embedding for.

    Returns:
        bool: True if successful, False otherwise.
    """
    from app.core.services.embedding import get_embedding_service

    try:
        embedding_service = get_embedding_service()
        embedding = embedding_service.generate_event_embedding(
            title=event.title,
            date=str(event.date) if event.date else None,
            venue=event.venue_name,
            description=event.description,
        )

        event.embedding = embedding
        await session.commit()

        logger.info("events.embedding_generated", event_id=str(event.id))
        return True
    except Exception as e:
        logger.error(
            "events.embedding_generation_failed",
            event_id=str(event.id),
            error=str(e),
        )
        return False

