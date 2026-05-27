"""KudaGo API ingestor - modern events aggregator with API.

Now uses AI-based extraction for accurate parsing instead of manual field mapping.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any, Optional
import json
import structlog
import httpx
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential_jitter
from redis import asyncio as aioredis

from app.core.services.quality import source_weight
from app.core.config import get_settings
from app.db.dao.events import upsert_event
from app.ingestors.normalize import clean_text
from app.ingestors.contact_extractor import extract_all_contacts, format_contacts_for_display
from app.ingestors.ai_parser_base import parse_event_with_ai, enqueue_parsed_event


logger = structlog.get_logger(module="ing.kudago")

# KudaGo API documentation: https://kudago.com/public-api/v1.4/
BASE_URL = "https://kudago.com/public-api/v1.4"

# Маппинг городов Крыма на KudaGo locations
CITY_LOCATIONS = {
    "севастополь": "sevastopol",
    "симферополь": "simferopol",
    "ялта": "yalta",
    "евпатория": "evpatoriya",
    "феодосия": "feodosia",
}

# Маппинг категорий KudaGo на наши
CATEGORY_MAP = {
    "concert": "concert",
    "party": "party",
    "exhibition": "expo",
    "theater": "theatre",
    "children": "kids",
    "tour": "tour",
    "business-events": "other",
    "education": "other",
    "festival": "concert",
    "holiday": "party",
    "quest": "other",
    "show": "theatre",
    "sport": "sport",
    "games": "kids",
}


async def fetch_events(city: str, days_ahead: int = 30) -> list[dict[str, Any]]:
    """Fetch events from KudaGo API for a specific city.

    Args:
        city: City name in Russian
        days_ahead: How many days ahead to fetch

    Returns:
        List of event dicts from API
    """
    location = CITY_LOCATIONS.get(city.strip().lower())
    if not location:
        logger.warning("kudago.city_not_supported", city=city)
        return []

    # Calculate date range
    today = datetime.now()
    since = int(today.timestamp())
    until = int((today + timedelta(days=days_ahead)).timestamp())

    url = f"{BASE_URL}/events/"
    params = {
        "location": location,
        "actual_since": since,
        "actual_until": until,
        "fields": "id,title,slug,dates,place,categories,description,body_text,price,is_free,images,site_url",
        "expand": "place",
        "page_size": 100,
        "order_by": "first_date",
    }

    events = []
    page = 1

    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            params["page"] = page
            try:
                logger.info("kudago.fetch_page", city=city, page=page)
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()

                results = data.get("results", [])
                if not results:
                    break

                events.extend(results)

                # Check if there's a next page
                if not data.get("next"):
                    break

                page += 1

                # Safety limit
                if page > 10:
                    logger.warning("kudago.page_limit_reached", city=city)
                    break

            except Exception as e:
                logger.error("kudago.fetch_error", city=city, page=page, error=str(e))
                break

    logger.info("kudago.fetched", city=city, count=len(events))
    return events


async def parse_event_with_ai_fallback(event: dict[str, Any], city: str) -> Optional[dict[str, Any]]:
    """Parse KudaGo event using AI with manual fallback.

    Args:
        event: Event dict from KudaGo API
        city: City name

    Returns:
        Parsed event dict or None if invalid
    """
    try:
        # Build rich text representation for AI
        # Include all important fields in a readable format
        title = event.get("title", "")
        description = event.get("description", "") or event.get("body_text", "")
        price = event.get("price", "Бесплатно" if event.get("is_free") else "Цена не указана")

        place_info = event.get("place", {})
        venue_name = place_info.get("title", "") if place_info else ""
        address = place_info.get("address", "") if place_info else ""

        # Get first date
        dates_info = event.get("dates", [])
        date_str = ""
        if dates_info:
            start_ts = dates_info[0].get("start")
            if start_ts:
                start_dt = datetime.fromtimestamp(start_ts)
                date_str = start_dt.strftime("%Y-%m-%d %H:%M")

        categories_list = event.get("categories", [])
        category_str = ", ".join(categories_list) if categories_list else ""

        # Build rich text for AI
        ai_input = f"""
Событие от KudaGo API:

Название: {title}
Дата и время: {date_str}
Место: {venue_name}
Адрес: {address}
Цена: {price}
Категории: {category_str}

Описание:
{description}

Город: {city}
"""

        # Get source URL
        site_url = event.get("site_url", "")
        if not site_url.startswith("http"):
            slug = event.get("slug", "")
            site_url = f"https://kudago.com/crimea/event/{slug}/"

        # Get image
        images = event.get("images", [])
        image_url = None
        if images:
            img = images[0]
            image_url = img.get("image") if isinstance(img, dict) else None

        # Parse with AI
        parsed = await parse_event_with_ai(
            text=ai_input,
            source_url=site_url,
            source_type="kudago_api",
            city=city,
            use_cache=True,
        )

        if not parsed:
            logger.warning("kudago.ai_parse_failed", event_id=event.get("id"), title=title)
            return None

        # Enrich with data AI might miss (coordinates, images)
        if place_info:
            coords = place_info.get("coords", {})
            if coords:
                parsed["lat"] = coords.get("lat")
                parsed["lon"] = coords.get("lon")

        if image_url:
            parsed["image_url"] = image_url

        parsed["kudago_id"] = event.get("id")

        return parsed

    except Exception as e:
        logger.error("kudago.parse_error", event_id=event.get("id"), error=str(e))
        return None


async def ingest(city: str, session) -> int:
    """Fetch and import events from KudaGo for a city using AI parsing.

    Args:
        city: City name in Russian
        session: Database session

    Returns:
        Number of events queued for moderation
    """
    events = []

    # Retry mechanism for fetching
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=2, max=30)
    ):
        with attempt:
            events = await fetch_events(city, days_ahead=60)

    if not events:
        logger.warning("kudago.no_events", city=city)
        return 0

    logger.info("kudago.parsing_with_ai", city=city, total_events=len(events))

    # Parse and queue events using AI
    queued = 0
    for event_data in events:
        try:
            parsed = await parse_event_with_ai_fallback(event_data, city)
            if not parsed:
                continue

            # Get image URL
            images = event_data.get("images", [])
            image_url = None
            if images:
                img = images[0]
                image_url = img.get("image") if isinstance(img, dict) else None

            # Get description for raw text
            description = event_data.get("description", "") or event_data.get("body_text", "")
            raw_text = f"{parsed['title']}\n\n{description}"

            # Enqueue the parsed event (auto-approved if configured)
            await enqueue_parsed_event(
                parsed_event=parsed,
                parser_name="kudago",
                raw_text=raw_text,
                image_url=image_url or parsed.get("image_url"),
                session=session,
            )

            queued += 1

        except Exception as e:
            logger.error("kudago.event_process_error", event_id=event_data.get("id"), error=str(e))
            continue

    logger.info("kudago.import_complete", city=city, total=len(events), queued=queued)
    return queued


if __name__ == "__main__":
    # Test script
    import asyncio
    from app.db.session import get_sessionmaker

    async def test():
        ss = get_sessionmaker()
        async with ss() as session:
            count = await ingest("Севастополь", session)
            print(f"Imported {count} events")

    asyncio.run(test())
