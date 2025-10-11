"""
Parser for sevastopol.kassa24.ru - Ticket booking platform for Sevastopol events.
"""
import asyncio
import json
import re
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.ext.asyncio import AsyncSession
from redis import asyncio as aioredis

from app.core.config import get_settings
from app.ingestors.contact_extractor import extract_all_contacts

BASE_URL = "https://sevastopol.kassa24.ru"

# Russian month mapping
MONTHS_RU = {
    "января": 1, "янв": 1,
    "февраля": 2, "фев": 2,
    "марта": 3, "мар": 3,
    "апреля": 4, "апр": 4,
    "мая": 5, "май": 5,
    "июня": 6, "июн": 6,
    "июля": 7, "июл": 7,
    "августа": 8, "авг": 8,
    "сентября": 9, "сен": 9,
    "октября": 10, "окт": 10,
    "ноября": 11, "ноя": 11,
    "декабря": 12, "дек": 12,
}


async def fetch_events_list() -> list[str]:
    """Fetch list of event URLs from multiple category pages."""
    event_urls = set()

    # Categories to scrape (from main page structure)
    categories = [
        "/event/index",     # All events
        "/event/index/1",   # Theatre
        "/event/index/2",   # Cinema
        "/event/index/4",   # Concert
        "/event/index/10",  # Excursions
        "/event/index/8",   # Show
        "/event/index/15",  # Children
    ]

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        for category in categories:
            try:
                url = f"{BASE_URL}{category}"
                resp = await client.get(url)
                resp.raise_for_status()

                soup = BeautifulSoup(resp.text, 'html.parser')

                # Find event links (pattern: /event/event-slug or //sevastopol.kassa24.ru/event/...)
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    # Handle both /event/ and full URLs
                    if '/event/' in href and not href.endswith('/event/index'):
                        if href.startswith('//'):
                            full_url = f"https:{href}"
                        elif href.startswith('/'):
                            full_url = f"{BASE_URL}{href}"
                        elif href.startswith('http'):
                            full_url = href
                        else:
                            continue

                        # Only add if it's an event detail page (not index)
                        if '/event/index' not in full_url:
                            event_urls.add(full_url)

                # Small delay between category requests
                await asyncio.sleep(0.5)

            except Exception as e:
                print(f"kassa24.category_error category={category} error={e}")
                continue

    result = list(event_urls)[:10]  # Limit to 10 per run to avoid timeout
    print(f"kassa24.found_urls count={len(result)}")
    return result


def parse_date(date_str: str) -> Optional[datetime]:
    """Parse Russian date string to datetime."""
    if not date_str:
        return None

    date_str = date_str.lower().strip()

    # Pattern: "26 декабря 2025"
    match = re.search(r'(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(\d{4})', date_str)
    if match:
        day = int(match.group(1))
        month = MONTHS_RU[match.group(2)]
        year = int(match.group(3))
        try:
            return datetime(year, month, day)
        except ValueError:
            return None

    # Pattern: "26.12.2025"
    match = re.search(r'(\d{1,2})\.(\d{1,2})\.(\d{4})', date_str)
    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        year = int(match.group(3))
        try:
            return datetime(year, month, day)
        except ValueError:
            return None

    return None


async def parse_event_page(url: str, client: httpx.AsyncClient) -> Optional[dict[str, Any]]:
    """Parse individual event page."""
    try:
        resp = await client.get(url)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, 'html.parser')

        # Extract title
        title_elem = soup.find('h1')
        if not title_elem:
            return None
        title = title_elem.get_text(strip=True)

        # Extract description
        description = ""
        desc_elem = soup.find('div', class_='event-description')
        if not desc_elem:
            desc_elem = soup.find('div', class_='description')
        if desc_elem:
            description = desc_elem.get_text(strip=True)

        # Extract date from meta description or page
        event_date = None

        # Try meta description (e.g., "18 октября 2025")
        meta_desc = soup.find('meta', {'name': 'description'})
        if meta_desc and meta_desc.get('content'):
            event_date = parse_date(meta_desc['content'])

        # Try date elements
        if not event_date:
            date_number = soup.find('strong', class_='event-date--number')
            date_month = soup.find('strong', class_='event-date--month')

            if date_number and date_month:
                try:
                    day = int(date_number.get_text(strip=True))
                    month_str = date_month.get_text(strip=True).lower()
                    month = MONTHS_RU.get(month_str)

                    if month:
                        # Determine year (current or next)
                        now = datetime.now()
                        year = now.year
                        temp_date = datetime(year, month, day)
                        if temp_date < now:
                            year += 1
                        event_date = datetime(year, month, day)
                except:
                    pass

        # Check for end date (for long-running events)
        end_date = None

        # Try to find end date in description or meta
        full_text = soup.get_text()

        # Patterns for end dates
        end_patterns = [
            r'до\s+(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(\d{4})',
            r'-\s*(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)',
            r'по\s+(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)',
        ]

        for pattern in end_patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                try:
                    day = int(match.group(1))
                    month = MONTHS_RU.get(match.group(2).lower())
                    if month:
                        year = event_date.year if len(match.groups()) < 3 else int(match.group(3))
                        end_date = datetime(year, month, day)
                        break
                except:
                    continue

        # Skip past events (but keep if end_date is in future)
        today = datetime.now()
        if end_date:
            if end_date < today:
                return None
            # Use end_date as event_date for better visibility
            event_date = end_date
        else:
            if event_date and event_date < today:
                return None
            elif not event_date:
                # If no date found, skip
                return None

        # Extract venue/location
        venue = "Севастополь"
        venue_elem = soup.find('div', class_='event-venue')
        if not venue_elem:
            venue_elem = soup.find('span', class_='venue')
        if venue_elem:
            venue = venue_elem.get_text(strip=True)

        # Extract price
        price = None
        is_free = False
        price_elem = soup.find('div', class_='event-price')
        if not price_elem:
            price_elem = soup.find('span', class_='price')

        if price_elem:
            price_text = price_elem.get_text(strip=True).lower()
            if 'бесплатно' in price_text or 'free' in price_text:
                is_free = True
                price = "Бесплатно"
            else:
                # Extract numeric price
                price_match = re.search(r'(\d+(?:\s?\d+)*)\s*(?:руб|₽|р)', price_text)
                if price_match:
                    price = price_match.group(1).replace(' ', '')

        # Extract image - Kassa24 uses <source> tags inside event-image div
        image_url = None

        # Try to find source tag with event image
        event_image_div = soup.find('div', id='event-image')
        if event_image_div:
            source_elem = event_image_div.find('source', type='image/jpeg')
            if not source_elem:
                source_elem = event_image_div.find('source')
            if source_elem:
                image_url = source_elem.get('srcset')

        # Fallback to meta og:image
        if not image_url:
            meta_img = soup.find('meta', {'property': 'og:image'})
            if meta_img:
                image_url = meta_img.get('content')

        # Make URL absolute
        if image_url and not image_url.startswith('http'):
            image_url = BASE_URL + image_url

        # Extract contacts from description and page
        full_text = f"{description} {soup.get_text()}"
        contacts = extract_all_contacts(full_text)

        # Build event data
        parsed = {
            "title": title,
            "description": description[:1000] if description else "",
            "date": event_date,
            "end_date": end_date,  # Date when event ends (for long-running events)
            "venue": venue,
            "price": price,
            "is_free": is_free,
            "image_url": image_url,
            "source_url": url,
            "contacts": contacts,
        }

        return parsed

    except Exception as e:
        print(f"kassa24.parse_error url={url} error={e}")
        return None


async def ingest(session: AsyncSession) -> int:
    """Main ingest function for Kassa24 parser."""
    settings = get_settings()
    redis = aioredis.from_url(str(settings.redis_url), decode_responses=True)

    # Fetch event URLs
    event_urls = await fetch_events_list()
    if not event_urls:
        print("kassa24.no_events")
        return 0

    queued_count = 0

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        for url in event_urls:
            try:
                parsed = await parse_event_page(url, client)
                if not parsed:
                    continue

                # Build form data (matching bot structure)
                # Extract price_min and price_max from price string
                price_min = 0
                price_max = None
                if parsed["price"] and not parsed["is_free"]:
                    # Try to parse price like "1200-3500" or "500"
                    price_str = str(parsed["price"])
                    if '-' in price_str:
                        parts = price_str.split('-')
                        try:
                            price_min = int(parts[0].strip())
                            price_max = int(parts[1].strip())
                        except:
                            try:
                                price_min = int(price_str.replace('-', '').strip())
                            except:
                                pass
                    else:
                        try:
                            price_min = int(price_str.strip())
                        except:
                            pass

                form = {
                    "title": parsed["title"],
                    "date_iso": parsed["date"].isoformat(),
                    "end_date_iso": parsed["end_date"].isoformat() if parsed.get("end_date") else None,  # Date when event ends
                    "time_24h": None,  # Kassa24 doesn't provide time separately
                    "city": "Севастополь",
                    "address": parsed.get("venue", ""),  # venue -> address
                    "lat": None,
                    "lon": None,
                    "price_min": price_min,
                    "price_max": price_max,
                    "category": "other",  # Kassa24 doesn't provide category
                    "source_url": parsed["source_url"],
                    # Contact info (additional fields)
                    "phone": parsed["contacts"].get("phone"),
                    "email": parsed["contacts"].get("email"),
                    "telegram": parsed["contacts"].get("telegram"),
                    "vk": parsed["contacts"].get("vk"),
                    "instagram": parsed["contacts"].get("instagram"),
                }

                # Add image if available
                images = []
                if parsed["image_url"]:
                    images.append(parsed["image_url"])

                # Build raw text for LLM enrichment
                raw_text = f"{parsed['title']}\n\n{parsed['description']}\n\nВремя: {parsed['date'].strftime('%d.%m.%Y')}\nМесто: {parsed['venue']}"
                if parsed["price"]:
                    raw_text += f"\nЦена: {parsed['price']}"

                # Queue payload
                payload = {
                    "form": form,
                    "raw_text": raw_text,
                    "source": "parser",
                    "parser_name": "kassa24",
                    "wants_paid_promotion": False,
                    "images": images,
                }

                # Add to parser queue
                await redis.lpush("ugc:queue:parser", json.dumps(payload, ensure_ascii=False))
                queued_count += 1

                # Small delay between requests
                await asyncio.sleep(0.3)

            except Exception as e:
                print(f"kassa24.ingest_error url={url} error={e}")
                continue

    print(f"kassa24.complete queued={queued_count}")
    return queued_count


async def main():
    """Test function for manual execution."""
    from app.db.session import get_sessionmaker

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        count = await ingest(session)
        print(f"Queued {count} events from Kassa24")


if __name__ == "__main__":
    asyncio.run(main())