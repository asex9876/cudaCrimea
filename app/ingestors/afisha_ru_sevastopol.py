"""
Parser for afisha.ru - Sevastopol section.
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

BASE_URL = "https://www.afisha.ru"

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
    """Fetch list of event URLs from Sevastopol section."""
    event_urls = set()

    # Categories to scrape for Sevastopol (reduced to avoid 429)
    categories = [
        "/sevastopol/schedule_concert",
        # "/sevastopol/schedule_theatre",  # Commented to reduce load
        # "/sevastopol/schedule_exhibition",
        # "/sevastopol/schedule_festival",
        # "/sevastopol/schedule_show",
    ]

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers=headers) as client:
        for category in categories:
            try:
                url = f"{BASE_URL}{category}"
                resp = await client.get(url)
                resp.raise_for_status()

                soup = BeautifulSoup(resp.text, 'html.parser')

                # Find event links (various patterns on afisha.ru)
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    # Event URLs usually contain /concert/, /exhibition/, etc.
                    if any(cat in href for cat in ['/concert/', '/exhibition/', '/festival/', '/show/', '/theatre/']):
                        if not href.startswith('http'):
                            full_url = f"{BASE_URL}{href}"
                        else:
                            full_url = href
                        # Only add Sevastopol events
                        if 'sevastopol' in full_url or 'севастополь' in full_url.lower():
                            event_urls.add(full_url)

                # Delay to avoid rate limiting (429 error)
                await asyncio.sleep(3.0)  # 3 seconds between categories

            except Exception as e:
                print(f"afisha_ru.category_error category={category} error={e}")
                continue

    result = list(event_urls)[:50]  # Limit to 50 per run
    print(f"afisha_ru.found_urls count={len(result)}")
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
        title_elem = soup.find('h1', class_='object-header-title')
        if not title_elem:
            title_elem = soup.find('h1')
        if not title_elem:
            return None
        title = title_elem.get_text(strip=True)

        # Extract description
        description = ""
        desc_elem = soup.find('div', class_='description')
        if not desc_elem:
            desc_elem = soup.find('div', class_='object-description')
        if desc_elem:
            description = desc_elem.get_text(strip=True)

        # Extract date from structured data or meta tags
        event_date = None

        # Try JSON-LD structured data
        script_elem = soup.find('script', {'type': 'application/ld+json'})
        if script_elem:
            try:
                json_data = json.loads(script_elem.string)
                if isinstance(json_data, dict) and 'startDate' in json_data:
                    event_date = datetime.fromisoformat(json_data['startDate'].replace('Z', '+00:00'))
                elif isinstance(json_data, list):
                    for item in json_data:
                        if 'startDate' in item:
                            event_date = datetime.fromisoformat(item['startDate'].replace('Z', '+00:00'))
                            break
            except:
                pass

        # Try meta tags
        if not event_date:
            date_elem = soup.find('meta', {'property': 'event:start_date'})
            if date_elem and date_elem.get('content'):
                try:
                    event_date = datetime.fromisoformat(date_elem['content'].replace('Z', '+00:00'))
                except:
                    pass

        # Try to find date in page text
        if not event_date:
            date_elem = soup.find('div', class_='event-date')
            if not date_elem:
                date_elem = soup.find('time')
            if date_elem:
                event_date = parse_date(date_elem.get_text())

        # Skip past events
        if event_date:
            today = datetime.now()
            if event_date < today:
                return None
        else:
            # If no date found, skip
            return None

        # Extract venue/location
        venue = "Севастополь"
        venue_elem = soup.find('div', class_='place-title')
        if not venue_elem:
            venue_elem = soup.find('a', class_='place-link')
        if venue_elem:
            venue = venue_elem.get_text(strip=True)

        # Extract price
        price = None
        is_free = False
        price_elem = soup.find('div', class_='price')
        if not price_elem:
            price_elem = soup.find('span', class_='price')

        if price_elem:
            price_text = price_elem.get_text(strip=True).lower()
            if 'бесплатно' in price_text or 'free' in price_text or 'вход свободный' in price_text:
                is_free = True
                price = "Бесплатно"
            else:
                # Extract numeric price
                price_match = re.search(r'(\d+(?:\s?\d+)*)\s*(?:руб|₽|р)', price_text)
                if price_match:
                    price = price_match.group(1).replace(' ', '')

        # Extract image
        image_url = None
        img_elem = soup.find('img', class_='object-header-image')
        if not img_elem:
            img_elem = soup.find('meta', {'property': 'og:image'})
            if img_elem:
                image_url = img_elem.get('content')
        else:
            image_url = img_elem.get('src')

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
            "venue": venue,
            "price": price,
            "is_free": is_free,
            "image_url": image_url,
            "source_url": url,
            "contacts": contacts,
        }

        return parsed

    except Exception as e:
        print(f"afisha_ru.parse_error url={url} error={e}")
        return None


async def ingest(session: AsyncSession) -> int:
    """Main ingest function for Afisha.ru parser."""
    settings = get_settings()
    redis = aioredis.from_url(str(settings.redis_url), decode_responses=True)

    # Fetch event URLs
    event_urls = await fetch_events_list()
    if not event_urls:
        print("afisha_ru.no_events")
        return 0

    queued_count = 0

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        for url in event_urls:
            try:
                parsed = await parse_event_page(url, client)
                if not parsed:
                    continue

                # Build form data
                form = {
                    "title": parsed["title"],
                    "date_iso": parsed["date"].isoformat(),
                    "venue": parsed["venue"],
                    "description": parsed["description"],
                    "phone": parsed["contacts"].get("phone"),
                    "email": parsed["contacts"].get("email"),
                    "telegram": parsed["contacts"].get("telegram"),
                    "vk": parsed["contacts"].get("vk"),
                    "instagram": parsed["contacts"].get("instagram"),
                    "price": parsed["price"],
                    "is_free": parsed["is_free"],
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
                    "parser_name": "afisha.ru",
                    "wants_paid_promotion": False,
                    "images": images,
                }

                # Add to parser queue
                await redis.lpush("ugc:queue:parser", json.dumps(payload, ensure_ascii=False))
                queued_count += 1

                # Small delay between requests
                await asyncio.sleep(0.3)

            except Exception as e:
                print(f"afisha_ru.ingest_error url={url} error={e}")
                continue

    print(f"afisha_ru.complete queued={queued_count}")
    return queued_count


async def main():
    """Test function for manual execution."""
    from app.db.session import get_sessionmaker

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        count = await ingest(session)
        print(f"Queued {count} events from Afisha.ru Sevastopol")


if __name__ == "__main__":
    asyncio.run(main())
