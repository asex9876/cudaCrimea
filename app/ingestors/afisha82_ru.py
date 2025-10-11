"""Afisha82.ru parser - main Crimean events portal."""

from __future__ import annotations

from datetime import datetime, timedelta, date, time
from typing import Any, Optional
import re
import structlog
import httpx
from bs4 import BeautifulSoup
import json
from redis import asyncio as aioredis

from app.core.config import get_settings
from app.ingestors.normalize import clean_text
from app.ingestors.contact_extractor import extract_all_contacts, format_contacts_for_display

logger = structlog.get_logger(module="ing.afisha82")

BASE_URL = "https://afisha82.ru"

# Category mapping
CATEGORY_MAP = {
    "концерты": "concert",
    "театр": "theatre",
    "для детей": "kids",
    "экскурсии": "tour",
    "вечеринки": "party",
    "выставки": "expo",
    "спорт": "sport",
    "фестивали": "party",
    "open air": "party",
}


async def fetch_events_list(page: int = 1) -> list[str]:
    """Fetch list of event URLs from the main page.

    Returns:
        List of relative event URLs
    """
    url = f"{BASE_URL}/"
    event_urls = []

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            logger.info("afisha82.fetch_list", page=page)
            resp = await client.get(url)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, 'html.parser')

            # Find all event links (they usually start with /number-name)
            for link in soup.find_all('a', href=True):
                href = link['href']
                # Event links have pattern /1234-event-name
                if re.match(r'/\d+-[\w-]+', href):
                    full_url = f"{BASE_URL}{href}"
                    if full_url not in event_urls:
                        event_urls.append(full_url)

            logger.info("afisha82.found_urls", count=len(event_urls))
            return event_urls[:50]  # Limit to 50 events per run

    except Exception as e:
        logger.error("afisha82.fetch_list_error", error=str(e))
        return []


async def parse_event_page(url: str) -> Optional[dict[str, Any]]:
    """Parse a single event page.

    Args:
        url: Full URL to event page

    Returns:
        Dict with event data or None
    """
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, 'html.parser')

            # Extract title
            title_tag = soup.find('h1')
            if not title_tag:
                return None
            title = clean_text(title_tag.get_text())

            # Extract description (all text content)
            description_parts = []
            for p in soup.find_all(['p', 'div'], class_=lambda x: x != 'header' if x else True):
                text = clean_text(p.get_text())
                if text and len(text) > 20:
                    description_parts.append(text)
            description = ' '.join(description_parts[:5])  # First 5 paragraphs
            if len(description) > 1000:
                description = description[:997] + "..."

            # Extract all text for contact and date parsing
            full_text = soup.get_text()

            # Extract dates (try multiple patterns)
            event_date = None
            event_time = None

            # Pattern 1: "26 сентября 2025" or "26.09.2025"
            date_patterns = [
                r'(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(\d{4})',
                r'(\d{1,2})\.(\d{1,2})\.(\d{4})',
                r'(\d{4})-(\d{1,2})-(\d{1,2})',
            ]

            for pattern in date_patterns:
                match = re.search(pattern, full_text)
                if match:
                    try:
                        if 'января' in match.group(0) or 'февраля' in match.group(0):
                            # Russian month names
                            months = {
                                'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4,
                                'мая': 5, 'июня': 6, 'июля': 7, 'августа': 8,
                                'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12
                            }
                            day = int(match.group(1))
                            month = months.get(match.group(2))
                            year = int(match.group(3))
                            event_date = date(year, month, day)
                        elif '.' in match.group(0):
                            # DD.MM.YYYY
                            day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
                            event_date = date(year, month, day)
                        else:
                            # YYYY-MM-DD
                            year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
                            event_date = date(year, month, day)
                        break
                    except:
                        continue

            # If no date found, try to find end date
            if not event_date:
                logger.warning("afisha82.no_date", url=url)
                return None

            # Check for end date (for long-running events)
            end_date = None
            end_patterns = [
                r'до\s+(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(\d{4})',
                r'-\s*(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)',
            ]

            months = {
                'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4,
                'мая': 5, 'июня': 6, 'июля': 7, 'августа': 8,
                'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12
            }

            for pattern in end_patterns:
                match = re.search(pattern, full_text)
                if match:
                    try:
                        day = int(match.group(1))
                        month = months.get(match.group(2))
                        year = event_date.year if len(match.groups()) < 3 else int(match.group(3))
                        end_date = date(year, month, day)
                        break
                    except:
                        continue

            # Skip past events (but keep if end_date is in future)
            today = datetime.now().date()
            if end_date:
                if end_date < today:
                    return None
                # Use end_date as event_date for better visibility
                event_date = end_date
            else:
                if event_date < today:
                    return None

            # Extract time (HH:MM)
            time_match = re.search(r'(\d{1,2}):(\d{2})', full_text)
            if time_match:
                try:
                    event_time = time(int(time_match.group(1)), int(time_match.group(2)))
                except:
                    pass

            # Extract price
            price_min = None
            price_max = None
            price_match = re.search(r'(\d+)\s*(?:руб|₽)', full_text, re.IGNORECASE)
            if price_match:
                price_min = int(price_match.group(1))

            # Check if free
            if re.search(r'бесплатн|вход\s+свободн', full_text, re.IGNORECASE):
                price_min = 0

            # Extract venue
            venue_name = "Не указано"
            venue_patterns = [
                r'(?:место|адрес|где)[:\s]+([^\n\.]{5,100})',
                r'(?:в|на)\s+([А-ЯЁ][а-яё\s-]{5,50})',
            ]
            for pattern in venue_patterns:
                match = re.search(pattern, full_text, re.IGNORECASE)
                if match:
                    venue_name = clean_text(match.group(1))
                    break

            # Detect city from text
            city = None
            cities = ['Севастополь', 'Симферополь', 'Ялта', 'Керчь', 'Евпатория', 'Феодосия']
            for c in cities:
                if c.lower() in full_text.lower():
                    city = c
                    break

            # Extract category
            category = "other"
            for cat_name, cat_code in CATEGORY_MAP.items():
                if cat_name in full_text.lower():
                    category = cat_code
                    break

            # Extract contacts
            contacts = extract_all_contacts(full_text)

            # Extract images
            image_url = None
            img_tag = soup.find('img', src=True)
            if img_tag and img_tag['src']:
                img_src = img_tag['src']
                if img_src.startswith('http'):
                    image_url = img_src
                elif img_src.startswith('/'):
                    image_url = f"{BASE_URL}{img_src}"

            return {
                "title": title,
                "date": event_date,
                "end_date": end_date,  # Date when event ends (for long-running events)
                "time": event_time,
                "venue_name": venue_name,
                "city": city,
                "price_min": price_min,
                "price_max": price_max,
                "category": category,
                "description": description,
                "image_url": image_url,
                "source_url": url,
                "contacts": contacts,
            }

    except Exception as e:
        logger.error("afisha82.parse_error", url=url, error=str(e))
        return None


async def ingest(session=None) -> int:
    """Fetch and queue events from afisha82.ru.

    Returns:
        Number of events queued
    """
    # Fetch event URLs
    event_urls = await fetch_events_list()

    if not event_urls:
        logger.warning("afisha82.no_urls")
        return 0

    # Get Redis connection
    settings = get_settings()
    redis = aioredis.from_url(str(settings.redis_url), decode_responses=True)

    queued = 0
    try:
        for url in event_urls:
            parsed = await parse_event_page(url)
            if not parsed:
                continue

            try:
                # Build form data (matching bot structure)
                form = {
                    "title": parsed["title"],
                    "date_iso": parsed["date"].isoformat(),
                    "end_date_iso": parsed["end_date"].isoformat() if parsed.get("end_date") else None,  # Date when event ends
                    "time_24h": parsed["time"].strftime("%H:%M") if parsed.get("time") else None,
                    "city": parsed.get("city", "Крым"),  # City
                    "address": parsed.get("venue_name", ""),  # venue_name -> address
                    "lat": None,  # Not available from parser
                    "lon": None,  # Not available from parser
                    "price_min": parsed.get("price_min", 0),
                    "price_max": parsed.get("price_max"),
                    "category": parsed.get("category", "other"),
                    "source_url": parsed["source_url"],
                    # Contact info (additional fields)
                    "phone": parsed["contacts"].get("phone"),
                    "email": parsed["contacts"].get("email"),
                    "telegram": parsed["contacts"].get("telegram"),
                    "vk": parsed["contacts"].get("vk"),
                    "instagram": parsed["contacts"].get("instagram"),
                }

                # Build raw text
                contacts_text = format_contacts_for_display(parsed["contacts"])
                raw_text = f"{parsed['title']}\n\n{parsed.get('description', '')}\n\n{contacts_text}"

                # Prepare images array (like bot does)
                images = []
                if parsed.get("image_url"):
                    images.append(parsed["image_url"])

                # Queue payload
                payload = {
                    "form": form,
                    "raw_text": raw_text,
                    "source_url": parsed["source_url"],
                    "images": images,  # Array of image URLs
                    "source": "parser",
                    "parser_name": "afisha82",
                    "wants_paid_promotion": False,
                    "ts": datetime.now().isoformat(),
                }

                # Add to parser queue
                await redis.lpush("ugc:queue:parser", json.dumps(payload, ensure_ascii=False))
                queued += 1
                logger.info("afisha82.queued", title=parsed["title"])

            except Exception as e:
                logger.error("afisha82.queue_error", title=parsed["title"], error=str(e))
                continue

    finally:
        await redis.aclose()

    logger.info("afisha82.complete", total=len(event_urls), queued=queued)
    return queued


if __name__ == "__main__":
    # Test
    import asyncio

    async def test():
        count = await ingest()
        print(f"Queued {count} events")

    asyncio.run(test())
