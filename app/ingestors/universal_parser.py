"""Universal AI-powered parser for any website.

Fetches HTML from any URL and uses AI to extract event information.
No manual selectors needed - AI figures out the structure automatically.
"""

from __future__ import annotations

import httpx
from datetime import datetime, timedelta
from typing import Any, Optional
from bs4 import BeautifulSoup

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import UniversalSource, Event
from app.core.config import get_settings
from app.db.dao.events import upsert_event
from app.core.services.geocoding import GeocodingService
from app.core.services.validation import get_validation_service
from app.core.services.embedding import get_embedding_service

logger = structlog.get_logger(module="universal_parser")


# Lazy imports
def _get_llm_client():
    from app.core.llm import client as llm_client
    return llm_client


def _get_event_draft():
    from app.core.llm.extractor import EventDraft
    return EventDraft


UNIVERSAL_PARSER_PROMPT = """Ты - эксперт по извлечению информации о событиях из веб-страниц.

Проанализируй HTML-код страницы и извлеки ВСЕ события, которые ты найдёшь.

ВАЖНО:
- Ищи все события на странице (концерты, спектакли, выставки, экскурсии и т.д.)
- Каждое событие должно быть в отдельном JSON-объекте
- Если на странице несколько событий - верни массив
- Если найдено только одно событие - верни массив из одного элемента
- Если событий нет - верни пустой массив []

Формат ответа - JSON массив объектов:
```json
[
  {
    "title": "название события",
    "date_iso": "YYYY-MM-DD",
    "time_24h": "HH:MM или null",
    "venue_name": "название места",
    "address": "адрес",
    "price_min": число или null,
    "price_max": число или null,
    "category": "concert|theatre|kids|tour|party|expo|other|sport",
    "age_restriction": "0+|6+|12+|16+|18+ или null",
    "organizer": "организатор или null",
    "end_time": "HH:MM или null",
    "duration_minutes": число или null,
    "ticket_type": "sale|booking|free|registration или null",
    "source_url": "ссылка на событие (если есть)"
  }
]
```

Извлекай только то, что явно указано. Не придумывай данные.
"""


async def fetch_html(url: str, timeout: int = 30) -> str:
    """Fetch HTML content from URL.

    Args:
        url: URL to fetch
        timeout: Request timeout in seconds

    Returns:
        HTML content as string

    Raises:
        httpx.HTTPError: If request fails
    """
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.text


def clean_html(html: str, max_length: int = 50000) -> str:
    """Clean and simplify HTML for AI processing.

    Args:
        html: Raw HTML
        max_length: Maximum length of output

    Returns:
        Cleaned HTML
    """
    soup = BeautifulSoup(html, 'html.parser')

    # Remove scripts, styles, comments
    for tag in soup(['script', 'style', 'noscript', 'iframe', 'svg']):
        tag.decompose()

    # Get text with some structure
    text = soup.get_text(separator='\n', strip=True)

    # Limit length
    if len(text) > max_length:
        text = text[:max_length] + "..."

    return text


async def parse_with_ai(html_content: str, source_url: str) -> list[dict[str, Any]]:
    """Parse HTML using AI to extract events.

    Args:
        html_content: HTML content
        source_url: Source URL for attribution

    Returns:
        List of event dictionaries
    """
    llm_client = _get_llm_client()
    settings = get_settings()

    # Clean HTML
    cleaned = clean_html(html_content)

    # Build prompt
    user_message = f"URL: {source_url}\n\nHTML содержимое:\n{cleaned}"

    messages = [
        {"role": "system", "content": UNIVERSAL_PARSER_PROMPT},
        {"role": "user", "content": user_message},
    ]

    try:
        # Call AI
        response = llm_client.chat_complete(
            model=settings.openai_model_extractor,
            messages=messages,
            temperature=0.1,
            service="universal_parser",
        )

        # Parse JSON response
        import json

        # Try to extract JSON array
        response = response.strip()

        # Remove markdown code blocks if present
        if response.startswith("```"):
            lines = response.split("\n")
            response = "\n".join(lines[1:-1]) if len(lines) > 2 else response
            response = response.replace("```json", "").replace("```", "").strip()

        events = json.loads(response)

        if not isinstance(events, list):
            events = [events]

        logger.info("universal_parser.ai_parsed", url=source_url, count=len(events))
        return events

    except Exception as e:
        logger.error("universal_parser.ai_parse_failed", url=source_url, error=str(e))
        return []


async def process_source(
    session: AsyncSession,
    source: UniversalSource,
) -> int:
    """Process a single universal source.

    Args:
        session: Database session
        source: UniversalSource to process

    Returns:
        Number of events successfully added
    """
    logger.info("universal_parser.processing", source_id=str(source.id), url=source.url)

    try:
        # Fetch HTML
        html = await fetch_html(source.url)

        # Parse with AI
        events_data = await parse_with_ai(html, source.url)

        if not events_data:
            logger.warning("universal_parser.no_events_found", url=source.url)
            await session.execute(
                update(UniversalSource)
                .where(UniversalSource.id == source.id)
                .values(
                    last_parsed_at=datetime.now(),
                    last_error=None,
                )
            )
            await session.commit()
            return 0

        # Process each event
        added_count = 0
        validator = get_validation_service()
        geocoding_service = GeocodingService(session)
        embedding_service = get_embedding_service()
        EventDraft = _get_event_draft()

        for event_data in events_data:
            try:
                # Validate with Pydantic
                draft = EventDraft.model_validate(event_data)

                if not draft.title or not draft.date_iso:
                    logger.warning("universal_parser.event_missing_required", title=draft.title)
                    continue

                # Parse dates
                from datetime import datetime as dt, date as d
                from dateparser import parse as parse_date

                event_date = parse_date(draft.date_iso)
                if not event_date:
                    logger.warning("universal_parser.invalid_date", date=draft.date_iso)
                    continue

                event_time = None
                if draft.time_24h:
                    try:
                        time_parts = draft.time_24h.split(":")
                        from datetime import time as dtime
                        event_time = dtime(int(time_parts[0]), int(time_parts[1]))
                    except:
                        pass

                end_time = None
                if draft.end_time:
                    try:
                        time_parts = draft.end_time.split(":")
                        from datetime import time as dtime
                        end_time = dtime(int(time_parts[0]), int(time_parts[1]))
                    except:
                        pass

                # Geocode address if provided
                lat, lon, district = None, None, None
                if draft.address:
                    geocode_result = await geocoding_service.geocode_address(
                        draft.address,
                        city=source.city or draft.venue_name,
                    )
                    if geocode_result:
                        lat, lon, district = geocode_result

                # Validate data
                validated_data = validator.validate_event_data({
                    "date": event_date.date() if hasattr(event_date, 'date') else event_date,
                    "time": event_time,
                    "end_time": end_time,
                    "duration_minutes": draft.duration_minutes,
                    "price_min": draft.price_min,
                    "price_max": draft.price_max,
                    "capacity": None,
                    "address": draft.address,
                })

                # Create event
                event = await upsert_event(
                    session,
                    title=draft.title,
                    date_=validated_data["date"],
                    time_=validated_data.get("time"),
                    city=source.city,
                    venue_name=draft.venue_name or "Не указано",
                    address=validated_data.get("address") or draft.address or "",
                    lat=lat,
                    lon=lon,
                    district=district,
                    price_min=validated_data.get("price_min"),
                    price_max=validated_data.get("price_max"),
                    category=draft.category or "other",
                    source=f"universal:{source.name}",
                    source_url=draft.source_url or source.url,
                    quality_base=0.7,  # Universal sources get medium quality
                )

                # Update extended fields
                event.age_restriction = draft.age_restriction
                event.organizer = draft.organizer
                event.end_time = validated_data.get("end_time")
                event.duration_minutes = validated_data.get("duration_minutes")
                event.ticket_type = draft.ticket_type

                # Generate embedding
                try:
                    embedding = embedding_service.generate_event_embedding(
                        title=event.title,
                        date=str(event.date),
                        venue=event.venue_name,
                        description=None,
                    )
                    event.embedding = embedding
                except Exception as e:
                    logger.warning("universal_parser.embedding_failed", error=str(e))

                added_count += 1
                logger.info("universal_parser.event_added", title=draft.title)

            except Exception as e:
                logger.error("universal_parser.event_process_failed", error=str(e), event=event_data)
                continue

        # Update source stats
        await session.execute(
            update(UniversalSource)
            .where(UniversalSource.id == source.id)
            .values(
                total_parsed=UniversalSource.total_parsed + added_count,
                last_parsed_at=datetime.now(),
                last_error=None,
            )
        )
        await session.commit()

        logger.info("universal_parser.completed", source_id=str(source.id), added=added_count)
        return added_count

    except Exception as e:
        error_msg = str(e)[:500]
        logger.error("universal_parser.source_failed", source_id=str(source.id), error=error_msg)

        # Update error
        await session.execute(
            update(UniversalSource)
            .where(UniversalSource.id == source.id)
            .values(
                last_parsed_at=datetime.now(),
                last_error=error_msg,
            )
        )
        await session.commit()
        return 0


async def process_all_active_sources(session: AsyncSession) -> dict[str, int]:
    """Process all active universal sources.

    Args:
        session: Database session

    Returns:
        Dict with stats: {"total_sources": N, "total_events": M}
    """
    # Get all active sources that need parsing
    now = datetime.now()

    stmt = select(UniversalSource).where(
        UniversalSource.is_active == True
    )

    result = await session.execute(stmt)
    sources = result.scalars().all()

    total_events = 0
    processed_sources = 0

    for source in sources:
        # Check if it's time to parse
        if source.last_parsed_at:
            next_parse_time = source.last_parsed_at + timedelta(minutes=source.parse_interval_minutes)
            if now < next_parse_time:
                continue  # Skip, not time yet

        # Process source
        events_added = await process_source(session, source)
        total_events += events_added
        processed_sources += 1

    logger.info(
        "universal_parser.batch_completed",
        sources=processed_sources,
        events=total_events,
    )

    return {
        "total_sources": processed_sources,
        "total_events": total_events,
    }
