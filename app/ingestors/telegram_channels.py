"""
Parser for Telegram channels with event announcements in Crimea.

Uses Telethon to read messages from public channels and extract event information.
Requires TELEGRAM_API_ID and TELEGRAM_API_HASH from https://my.telegram.org/apps
"""
import asyncio
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from redis import asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession
from telethon import TelegramClient
from telethon.tl.types import Message

from app.core.config import get_settings
from app.ingestors.contact_extractor import extract_all_contacts


# Crimean event channels to monitor
CRIMEA_CHANNELS = [
    "simferopol_afisha",
    "yalta_afisha",
    "sevastopol_events",
    "crimea_events",
    "krym_afisha",
    # Add more channels here
]

# Russian month names for date parsing
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

# Keywords that indicate an event announcement
EVENT_KEYWORDS = [
    "концерт", "выставка", "фестиваль", "мероприятие", "событие",
    "спектакль", "шоу", "встреча", "мастер-класс", "экскурсия",
    "вечеринка", "party", "афиша", "приглашаем", "ждём", "билеты",
]


def parse_date_from_text(text: str) -> Optional[datetime]:
    """Extract date from Russian text."""
    if not text:
        return None

    text_lower = text.lower()

    # Pattern: "15 октября" or "15 октября 2025"
    pattern = r'(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)(?:\s+(\d{4}))?'
    match = re.search(pattern, text_lower)

    if match:
        day = int(match.group(1))
        month = MONTHS_RU[match.group(2)]
        year = int(match.group(3)) if match.group(3) else datetime.now(timezone.utc).year

        try:
            event_date = datetime(year, month, day, tzinfo=timezone.utc)

            # If date is in the past, assume next year
            if event_date < datetime.now(timezone.utc):
                event_date = datetime(year + 1, month, day, tzinfo=timezone.utc)

            return event_date
        except ValueError:
            pass

    # Pattern: "сегодня" or "завтра"
    if "сегодня" in text_lower:
        return datetime.now(timezone.utc)
    elif "завтра" in text_lower:
        return datetime.now(timezone.utc) + timedelta(days=1)

    return None


def parse_time_from_text(text: str) -> Optional[str]:
    """Extract time from text (HH:MM format)."""
    if not text:
        return None

    # Pattern: "19:00" or "в 19:00"
    match = re.search(r'(?:в\s+)?(\d{1,2}):(\d{2})', text)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"

    return None


def parse_price_from_text(text: str) -> tuple[int, Optional[int], bool]:
    """Extract price information from text. Returns (price_min, price_max, is_free)."""
    if not text:
        return (0, None, False)

    text_lower = text.lower()

    # Check if free
    if any(word in text_lower for word in ["бесплатно", "free", "вход свободный"]):
        return (0, None, True)

    # Pattern: "от 500 руб" or "500-1000 руб" or "500₽"
    price_patterns = [
        r'(\d+)\s*-\s*(\d+)\s*(?:руб|₽|р)',  # Range: 500-1000
        r'от\s+(\d+)\s*(?:до\s+(\d+))?\s*(?:руб|₽|р)',  # от 500 до 1000
        r'(\d+)\s*(?:руб|₽|р)',  # Single: 500
    ]

    for pattern in price_patterns:
        match = re.search(pattern, text_lower)
        if match:
            if match.lastindex == 2 and match.group(2):
                # Range
                return (int(match.group(1)), int(match.group(2)), False)
            else:
                # Single price
                return (int(match.group(1)), None, False)

    return (0, None, False)


def extract_city_from_text(text: str) -> str:
    """Extract city name from text."""
    if not text:
        return "Крым"

    text_lower = text.lower()

    cities = {
        "симферополь": "Симферополь",
        "севастополь": "Севастополь",
        "ялта": "Ялта",
        "алушта": "Алушта",
        "евпатория": "Евпатория",
        "феодосия": "Феодосия",
        "керчь": "Керчь",
        "судак": "Судак",
        "бахчисарай": "Бахчисарай",
    }

    for city_key, city_name in cities.items():
        if city_key in text_lower:
            return city_name

    return "Крым"


def is_event_message(message: Message) -> bool:
    """Check if message contains event announcement."""
    if not message.message:
        return False

    text_lower = message.message.lower()

    # Must contain at least one event keyword
    return any(keyword in text_lower for keyword in EVENT_KEYWORDS)


async def download_message_photo(client: TelegramClient, message: Message) -> Optional[str]:
    """
    Download photo from Telegram message and save to uploads directory.

    Args:
        client: Telethon client
        message: Telegram message with photo

    Returns:
        Relative path to saved image or None
    """
    if not message.photo:
        return None

    try:
        # Create uploads directory if it doesn't exist
        uploads_dir = Path("/app/app/uploads")
        uploads_dir.mkdir(parents=True, exist_ok=True)

        # Generate unique filename
        file_ext = "jpg"
        filename = f"tg_{message.id}_{uuid.uuid4().hex[:8]}.{file_ext}"
        file_path = uploads_dir / filename

        # Download photo (use message directly to get full size, not message.photo)
        await client.download_media(message, file=str(file_path))

        # Verify file was downloaded and has content
        if not file_path.exists() or file_path.stat().st_size == 0:
            print(f"telegram.photo_empty message_id={message.id}")
            if file_path.exists():
                file_path.unlink()  # Delete empty file
            return None

        print(f"telegram.photo_downloaded message_id={message.id} size={file_path.stat().st_size}")

        # Return relative path for database
        return f"/uploads/{filename}"

    except Exception as e:
        print(f"telegram.photo_download_error message_id={message.id} error={e}")
        return None


async def parse_message(message: Message, channel_name: str, client: TelegramClient) -> Optional[dict[str, Any]]:
    """Parse Telegram message into event data."""
    if not message.message:
        return None

    text = message.message

    # Extract event date
    event_date = parse_date_from_text(text)
    if not event_date:
        # If no date found, skip (not a valid event)
        return None

    # Skip past events
    if event_date < datetime.now(timezone.utc):
        return None

    # Extract title (first line usually)
    lines = text.split('\n')
    title = lines[0].strip() if lines else "Событие"

    # Limit title length
    if len(title) > 200:
        title = title[:200]

    # Extract time
    event_time = parse_time_from_text(text)

    # Extract price
    price_min, price_max, is_free = parse_price_from_text(text)

    # Extract city
    city = extract_city_from_text(text)

    # Extract contacts
    contacts = extract_all_contacts(text)

    # Download photos
    photo_path = await download_message_photo(client, message)
    images = [photo_path] if photo_path else []

    # Build event data
    event = {
        "title": title,
        "description": text[:1000],  # Limit description
        "date": event_date,
        "time": event_time,
        "city": city,
        "price_min": price_min,
        "price_max": price_max,
        "is_free": is_free,
        "contacts": contacts,
        "source_url": f"https://t.me/{channel_name}/{message.id}",
        "channel_name": channel_name,
        "message_id": message.id,
        "images": images,
    }

    return event


async def ingest(session: AsyncSession, limit_days: int = 7) -> int:
    """
    Main ingest function for Telegram channels.

    Args:
        session: Database session
        limit_days: How many days back to fetch messages (default: 7)

    Returns:
        Number of events queued
    """
    settings = get_settings()

    # Get selected account from runtime config
    from app.db.models import TelegramAccount
    from sqlalchemy import select
    from telethon.sessions import StringSession
    from app.core import runtime_config as rc
    import uuid

    selected_account_id = rc.get("tg_account_id")
    account = None

    if selected_account_id:
        # Try to get the selected account
        try:
            account = await session.get(TelegramAccount, uuid.UUID(selected_account_id))
            if account and account.status != "active":
                account = None
        except (ValueError, TypeError):
            pass

    if not account:
        # Fallback: get any active account
        account = (await session.execute(
            select(TelegramAccount)
            .where(TelegramAccount.is_active == True)
            .where(TelegramAccount.status == "active")
            .limit(1)
        )).scalar_one_or_none()

    if not account:
        # No accounts available
        print("telegram.error: No active Telegram account configured")
        print("Add account in admin panel: /admin/telegram-accounts")
        return 0

    # Use saved session from database
    print(f"telegram.using_account phone={account.phone} user={account.first_name}")
    client = TelegramClient(
        StringSession(account.session_string),
        account.api_id,
        account.api_hash
    )

    redis = aioredis.from_url(str(settings.redis_url), decode_responses=True)
    queued_count = 0

    try:
        await client.connect()
        if not await client.is_user_authorized():
            print("telegram.error: Session expired or not authorized")
            print("Re-authorize in admin panel: /admin/telegram-accounts")
            return 0

        me = await client.get_me()
        print(f"telegram.connected user_id={me.id} name={me.first_name}")

        # Calculate date limit (timezone-aware)
        since_date = datetime.now(timezone.utc) - timedelta(days=limit_days)

        # Get channels from runtime config or use defaults
        channels = rc.get("ingest_tg_channels", CRIMEA_CHANNELS)
        if not channels:
            channels = CRIMEA_CHANNELS

        print(f"telegram.channels count={len(channels)} channels={channels}")

        # Fetch messages from each channel
        for channel_username in channels:
            try:
                print(f"telegram.fetching channel={channel_username}")

                # Get channel entity
                try:
                    channel = await client.get_entity(channel_username)
                except Exception as e:
                    print(f"telegram.channel_not_found channel={channel_username} error={e}")
                    continue

                # Fetch recent messages
                messages = await client.get_messages(
                    channel,
                    limit=100,  # Last 100 messages
                )

                parsed_count = 0

                for message in messages:
                    # Skip old messages
                    if message.date < since_date:
                        continue

                    # Check if it's an event announcement
                    if not is_event_message(message):
                        continue

                    # Parse message
                    event = await parse_message(message, channel_username, client)
                    if not event:
                        continue

                    # Build form data (matching bot structure)
                    form = {
                        "title": event["title"],
                        "date_iso": event["date"].isoformat(),
                        "end_date_iso": None,
                        "time_24h": event.get("time"),
                        "city": event["city"],
                        "address": "",
                        "lat": None,
                        "lon": None,
                        "price_min": event["price_min"],
                        "price_max": event["price_max"],
                        "category": "other",
                        "source_url": event["source_url"],
                        # Contact info
                        "phone": event["contacts"].get("phone"),
                        "email": event["contacts"].get("email"),
                        "telegram": event["contacts"].get("telegram"),
                        "vk": event["contacts"].get("vk"),
                        "instagram": event["contacts"].get("instagram"),
                    }

                    # Build raw text
                    raw_text = f"{event['title']}\n\n{event['description']}"
                    if event.get("time"):
                        raw_text += f"\n\nВремя: {event['time']}"
                    raw_text += f"\nГород: {event['city']}"

                    # Queue payload
                    payload = {
                        "form": form,
                        "raw_text": raw_text,
                        "source": "parser",
                        "parser_name": f"telegram:{channel_username}",
                        "wants_paid_promotion": False,
                        "images": event.get("images", []),
                    }

                    # Add to parser queue
                    await redis.lpush("ugc:queue:parser", json.dumps(payload, ensure_ascii=False))
                    queued_count += 1
                    parsed_count += 1

                print(f"telegram.channel_done channel={channel_username} parsed={parsed_count}")

                # Small delay between channels
                await asyncio.sleep(1)

            except Exception as e:
                print(f"telegram.channel_error channel={channel_username} error={e}")
                continue

    finally:
        await client.disconnect()

    print(f"telegram.complete queued={queued_count}")
    return queued_count


async def main():
    """Test function for manual execution."""
    from app.db.session import get_sessionmaker

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        count = await ingest(session, limit_days=7)
        print(f"Queued {count} events from Telegram channels")


if __name__ == "__main__":
    asyncio.run(main())
