"""KudaGo API ingestor - modern events aggregator with API."""

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


def parse_event(event: dict[str, Any], city: str) -> Optional[dict[str, Any]]:
    """Parse a single KudaGo event into our format.

    Args:
        event: Event dict from KudaGo API
        city: City name

    Returns:
        Parsed event dict or None if invalid
    """
    try:
        title = clean_text(event.get("title", ""))
        if not title:
            return None

        # Parse dates
        dates_info = event.get("dates", [])
        if not dates_info:
            return None

        # Get first occurrence
        first_date_info = dates_info[0]
        start_timestamp = first_date_info.get("start")
        if not start_timestamp:
            return None

        start_dt = datetime.fromtimestamp(start_timestamp)
        event_date = start_dt.date()
        event_time = start_dt.time()

        # Parse place
        place_info = event.get("place", {})
        venue_name = ""
        address = ""
        lat = None
        lon = None

        if place_info:
            venue_name = clean_text(place_info.get("title", ""))
            address = clean_text(place_info.get("address", ""))
            coords = place_info.get("coords", {})
            if coords:
                lat = coords.get("lat")
                lon = coords.get("lon")

        # Parse price
        price_str = event.get("price", "")
        is_free = event.get("is_free", False)
        price_min = None
        price_max = None

        if is_free:
            price_min = 0
        elif price_str:
            # Try to extract numbers from price string
            import re
            numbers = re.findall(r'\d+', str(price_str))
            if numbers:
                price_min = int(numbers[0])
                if len(numbers) > 1:
                    price_max = int(numbers[-1])

        # Parse category
        categories = event.get("categories", [])
        category = "other"
        if categories:
            first_cat_slug = categories[0] if isinstance(categories[0], str) else ""
            category = CATEGORY_MAP.get(first_cat_slug, "other")

        # Get description and images
        description = clean_text(event.get("description", "") or event.get("body_text", ""))
        if len(description) > 1000:
            description = description[:997] + "..."

        # Get first image URL
        images = event.get("images", [])
        image_url = None
        if images:
            img = images[0]
            image_url = img.get("image") if isinstance(img, dict) else None

        # Source URL
        site_url = event.get("site_url", "")
        if not site_url.startswith("http"):
            slug = event.get("slug", "")
            site_url = f"https://kudago.com/crimea/event/{slug}/"

        return {
            "title": title,
            "date": event_date,
            "time": event_time,
            "venue_name": venue_name or "Не указано",
            "address": address,
            "lat": lat,
            "lon": lon,
            "price_min": price_min,
            "price_max": price_max,
            "is_free": is_free,
            "category": category,
            "description": description,
            "image_url": image_url,
            "source_url": site_url,
            "kudago_id": event.get("id"),
        }

    except Exception as e:
        logger.error("kudago.parse_error", event_id=event.get("id"), error=str(e))
        return None


async def ingest(city: str, session) -> int:
    """Fetch and import events from KudaGo for a city.

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

    # Get Redis connection
    settings = get_settings()
    redis = aioredis.from_url(str(settings.redis_url), decode_responses=True)

    # Parse and queue events for moderation
    queued = 0
    try:
        for event_data in events:
            parsed = parse_event(event_data, city)
            if not parsed:
                continue

            try:
                # Extract contacts from description and source URL
                full_text = f"{parsed.get('description', '')} {parsed.get('source_url', '')}"
                contacts = extract_all_contacts(full_text)

                # Build structured form
                form = {
                    "title": parsed["title"],
                    "date_iso": parsed["date"].isoformat(),
                    "time_24h": parsed["time"].strftime("%H:%M") if parsed.get("time") else None,
                    "venue_name": parsed["venue_name"],
                    "city": city,
                    "address": parsed.get("address"),
                    "lat": parsed.get("lat"),
                    "lon": parsed.get("lon"),
                    "price_min": parsed.get("price_min"),
                    "price_max": parsed.get("price_max"),
                    "category": parsed["category"],
                    "source_url": parsed["source_url"],
                    # Contact info
                    "phone": contacts.get("phone"),
                    "email": contacts.get("email"),
                    "telegram": contacts.get("telegram"),
                    "vk": contacts.get("vk"),
                    "instagram": contacts.get("instagram"),
                }

                # Build raw text for display
                contacts_text = format_contacts_for_display(contacts)
                raw_text = f"{parsed['title']}\n\n{parsed.get('description', '')}\n\n{contacts_text}"

                # Queue payload
                payload = {
                    "form": form,
                    "raw_text": raw_text,
                    "source_url": parsed["source_url"],
                    "image_url": parsed.get("image_url"),
                    "source": "parser",  # Mark as parsed event
                    "parser_name": "kudago",
                    "wants_paid_promotion": False,
                    "ts": datetime.now().isoformat(),
                }

                # Add to parser queue (separate queue for parsed events)
                await redis.lpush("ugc:queue:parser", json.dumps(payload, ensure_ascii=False))
                queued += 1

            except Exception as e:
                logger.error("kudago.queue_error", title=parsed["title"], error=str(e))
                continue

    finally:
        await redis.aclose()

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
