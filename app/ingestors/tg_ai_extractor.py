"""AI-powered event extraction from Telegram channel posts."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, time as dtime, timedelta
from typing import Any, Optional
import structlog
import httpx

from app.core.config import get_settings
from app.ingestors.normalize import clean_text, parse_date, parse_time


logger = structlog.get_logger(module="ing.tg_ai")


EXTRACTION_PROMPT = """Ты помощник, который извлекает информацию о событиях из постов в Telegram каналах.

Проанализируй следующий пост и извлеки информацию о событии в формате JSON.

Пост:
{post_text}

Извлеки следующую информацию (если найдена):
- title: название события
- date: дата события (формат YYYY-MM-DD)
- time: время события (формат HH:MM)
- venue: название места проведения
- address: адрес
- price_min: минимальная цена (число, рубли)
- price_max: максимальная цена (число, рубли)
- is_free: бесплатно ли (true/false)
- category: категория события (concert, theatre, kids, tour, party, expo, sport, other)
- description: краткое описание события

Если информация не найдена, укажи null.
Если это НЕ событие (просто пост, реклама, новость), верни {{"is_event": false}}.

Верни только валидный JSON, без дополнительных комментариев."""


async def extract_event_with_ai(post_text: str) -> Optional[dict[str, Any]]:
    """Use AI to extract event information from a Telegram post.

    Args:
        post_text: Raw text from Telegram post

    Returns:
        Extracted event dict or None if not an event
    """
    settings = get_settings()

    # Используем AI Mediator API (или OpenAI)
    api_key = settings.ai_mediator_api_key or settings.openai_api_key
    base_url = settings.ai_mediator_base_url or settings.openai_base_url
    model = settings.openai_model_extractor or "gpt-4o-mini"

    if not api_key or not base_url:
        logger.warning("tg_ai.no_api_key")
        return None

    prompt = EXTRACTION_PROMPT.format(post_text=post_text[:2000])  # Limit text length

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "You are a helpful assistant that extracts event information from text."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 500,
                },
            )
            response.raise_for_status()
            data = response.json()

            # Extract JSON from response
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            # Try to parse JSON from response
            # Sometimes AI returns ```json ... ``` format
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                event_data = json.loads(json_match.group(0))

                # Check if it's actually an event
                if event_data.get("is_event") is False:
                    logger.info("tg_ai.not_event", post_preview=post_text[:100])
                    return None

                return event_data

            logger.warning("tg_ai.no_json_in_response", content=content[:200])
            return None

    except Exception as e:
        logger.error("tg_ai.extraction_error", error=str(e), post_preview=post_text[:100])
        return None


def parse_extracted_event(extracted: dict[str, Any], channel: str) -> Optional[dict[str, Any]]:
    """Convert AI-extracted data to our event format.

    Args:
        extracted: Dict from AI extraction
        channel: Telegram channel name

    Returns:
        Event dict in our format or None
    """
    try:
        title = extracted.get("title")
        if not title or len(title) < 5:
            return None

        # Parse date
        date_str = extracted.get("date")
        event_date = None
        if date_str:
            event_date = parse_date(date_str)
        if not event_date:
            # Default to tomorrow if no date found
            event_date = (datetime.now() + timedelta(days=1)).date()

        # Parse time
        time_str = extracted.get("time")
        event_time = parse_time(time_str) if time_str else None

        # Parse venue and address
        venue = clean_text(extracted.get("venue", "")) or "Не указано"
        address = clean_text(extracted.get("address", "")) or None

        # Parse price
        price_min = extracted.get("price_min")
        price_max = extracted.get("price_max")
        is_free = extracted.get("is_free", False)

        if is_free:
            price_min = 0
            price_max = 0

        # Category
        category = extracted.get("category", "other")
        valid_categories = {"concert", "theatre", "kids", "tour", "party", "expo", "sport", "other"}
        if category not in valid_categories:
            category = "other"

        # Description
        description = clean_text(extracted.get("description", ""))
        if len(description) > 500:
            description = description[:497] + "..."

        return {
            "title": title,
            "date": event_date,
            "time": event_time,
            "venue_name": venue,
            "address": address,
            "price_min": price_min,
            "price_max": price_max,
            "is_free": is_free,
            "category": category,
            "description": description,
            "source": "telegram",
            "source_channel": channel,
        }

    except Exception as e:
        logger.error("tg_ai.parse_error", error=str(e), extracted=extracted)
        return None


async def process_telegram_post(post: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Process a single Telegram post and extract event if present.

    Args:
        post: Post dict with 'channel', 'text', 'ts'

    Returns:
        Parsed event dict or None
    """
    text = post.get("text", "")
    channel = post.get("channel", "unknown")

    if not text or len(text) < 20:
        return None

    # Use AI to extract event data
    extracted = await extract_event_with_ai(text)
    if not extracted:
        return None

    # Convert to our format
    event = parse_extracted_event(extracted, channel)
    if not event:
        return None

    logger.info("tg_ai.event_extracted",
                channel=channel,
                title=event.get("title"),
                date=str(event.get("date")))

    return event


# === CATEGORY CLASSIFICATION ===

CLASSIFICATION_PROMPT = """Определи категорию события по его названию и описанию.

Название: {title}
Описание: {description}

Доступные категории:
- concert: концерты, живая музыка, выступления музыкантов
- theatre: театр, спектакли, представления
- kids: детские мероприятия, детские праздники
- tour: экскурсии, туры, прогулки
- party: вечеринки, дискотеки, клубные мероприятия
- expo: выставки, галереи, экспозиции
- sport: спортивные мероприятия, соревнования
- other: остальное

Верни только одно слово - название категории."""


async def classify_category_with_ai(title: str, description: str = "") -> str:
    """Use AI to classify event category.

    Args:
        title: Event title
        description: Event description

    Returns:
        Category name (concert, theatre, kids, etc.)
    """
    settings = get_settings()

    api_key = settings.ai_mediator_api_key or settings.openai_api_key
    base_url = settings.ai_mediator_base_url or settings.openai_base_url
    model = settings.openai_model_classifier or "gpt-4o-mini"

    if not api_key or not base_url:
        return "other"

    prompt = CLASSIFICATION_PROMPT.format(title=title[:200], description=description[:300])

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "You are a helpful assistant for event classification."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 20,
                },
            )
            response.raise_for_status()
            data = response.json()

            content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip().lower()

            # Validate category
            valid_categories = {"concert", "theatre", "kids", "tour", "party", "expo", "sport", "other"}
            if content in valid_categories:
                return content

            return "other"

    except Exception as e:
        logger.error("tg_ai.classification_error", error=str(e))
        return "other"


if __name__ == "__main__":
    # Test script
    import asyncio

    async def test():
        sample_post = """
        🎵 Концерт группы "Крым-Рок"

        📅 15 декабря в 19:00
        📍 ДК "Севастополь", ул. Ленина 10
        💰 500-1000₽

        Приходите на грандиозное выступление!
        """

        result = await extract_event_with_ai(sample_post)
        print("Extracted:", json.dumps(result, ensure_ascii=False, indent=2))

        if result:
            parsed = parse_extracted_event(result, "@test_channel")
            print("\nParsed:", json.dumps(parsed, ensure_ascii=False, indent=2, default=str))

    asyncio.run(test())
