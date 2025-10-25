"""Unified AI-based parser for all event sources.

This module provides utilities for parsing events from websites
using AI for accurate data extraction.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time as dtime, timedelta
from typing import Any, Optional

import structlog
from redis import asyncio as aioredis

from app.core.config import get_settings
from app.core.llm.is_event_classifier import classify
from app.core.llm.extractor import extract_event_fields, EventDraft
from app.ingestors.normalize import clean_text, parse_date, parse_time
from app.ingestors.contact_extractor import extract_all_contacts, format_contacts_for_display


logger = structlog.get_logger(module="ing.ai_parser")


# Cache TTL for AI parsing results (24 hours)
CACHE_TTL_SECONDS = 86400


def _cache_key(text: str) -> str:
    """Generate cache key from text content hash."""
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"ai_parse:{content_hash}"


async def _get_cached_result(redis: aioredis.Redis, text: str) -> Optional[dict[str, Any]]:
    """Get cached AI parsing result if available."""
    try:
        key = _cache_key(text)
        cached = await redis.get(key)
        if cached:
            logger.debug("ai_parser.cache_hit", key=key)
            return json.loads(cached)
    except Exception as e:
        logger.warning("ai_parser.cache_get_error", error=str(e))
    return None


async def _cache_result(redis: aioredis.Redis, text: str, result: dict[str, Any]) -> None:
    """Cache AI parsing result."""
    try:
        key = _cache_key(text)
        await redis.setex(key, CACHE_TTL_SECONDS, json.dumps(result, ensure_ascii=False, default=str))
        logger.debug("ai_parser.cache_set", key=key)
    except Exception as e:
        logger.warning("ai_parser.cache_set_error", error=str(e))


async def parse_event_with_ai(
    text: str,
    source_url: Optional[str] = None,
    source_type: str = "unknown",
    city: Optional[str] = None,
    use_cache: bool = True,
) -> Optional[dict[str, Any]]:
    """Parse event from raw text using AI (2-stage: classify → extract).

    Args:
        text: Raw text content (HTML, plain text, JSON string, etc.)
        source_url: Optional source URL
        source_type: Type of source (telegram, website, api, etc.)
        city: City name if known
        use_cache: Whether to use Redis cache for results

    Returns:
        Parsed event dict in our format, or None if not an event or parsing failed
    """
    if not text or len(text.strip()) < 20:
        return None

    # Clean text for better AI processing
    clean_input = clean_text(text)
    if len(clean_input) < 20:
        return None

    settings = get_settings()
    redis = aioredis.from_url(str(settings.redis_url), decode_responses=True)

    try:
        # Check cache first
        if use_cache:
            cached = await _get_cached_result(redis, clean_input)
            if cached:
                return cached

        # STAGE 1: Classify if this is an event
        logger.info("ai_parser.classifying", source_type=source_type, text_len=len(clean_input))
        classification = classify(clean_input[:2000])  # Limit input size

        if not classification.is_event:
            logger.info("ai_parser.not_event", source_type=source_type, reasons=classification.reasons)
            # Cache negative result to avoid re-processing
            if use_cache:
                await _cache_result(redis, clean_input, {"is_event": False})
            return None

        # STAGE 2: Extract event fields
        logger.info("ai_parser.extracting", source_type=source_type)
        extracted: EventDraft = extract_event_fields(clean_input[:3000], source_url=source_url)

        # Validate required fields
        if not extracted.title or len(extracted.title) < 5:
            logger.warning("ai_parser.no_title", source_type=source_type)
            return None

        # Parse date (default to tomorrow if missing)
        event_date: Optional[date] = None
        if extracted.date_iso:
            event_date = parse_date(extracted.date_iso)
        if not event_date:
            event_date = (datetime.now() + timedelta(days=1)).date()

        # Parse time
        event_time: Optional[dtime] = None
        if extracted.time_24h:
            event_time = parse_time(extracted.time_24h)

        # Venue and address
        venue_name = extracted.venue_name or "Не указано"
        address = extracted.address

        # Price
        price_min = extracted.price_min
        price_max = extracted.price_max
        is_free = (price_min == 0 and price_max == 0) if price_min is not None else False

        # Category
        category = extracted.category or "other"
        valid_categories = {"concert", "theatre", "kids", "tour", "party", "expo", "sport", "other"}
        if category not in valid_categories:
            category = "other"

        # Extract contacts from text
        contacts = extract_all_contacts(clean_input)

        # Build result
        result = {
            "title": extracted.title,
            "date": event_date,
            "time": event_time,
            "venue_name": venue_name,
            "address": address,
            "price_min": price_min,
            "price_max": price_max,
            "is_free": is_free,
            "category": category,
            "source_url": source_url or extracted.source_url,
            "source_type": source_type,
            "city": city,
            # Contact info
            "phone": contacts.get("phone"),
            "email": contacts.get("email"),
            "telegram": contacts.get("telegram"),
            "vk": contacts.get("vk"),
            "instagram": contacts.get("instagram"),
        }

        # Cache successful result
        if use_cache:
            await _cache_result(redis, clean_input, result)

        logger.info(
            "ai_parser.success",
            source_type=source_type,
            title=result["title"],
            date=str(result["date"]),
            category=result["category"],
        )

        return result

    except Exception as e:
        logger.error("ai_parser.error", source_type=source_type, error=str(e), text_preview=clean_input[:100])
        return None

    finally:
        await redis.aclose()


async def enqueue_parsed_event(
    parsed_event: dict[str, Any],
    parser_name: str,
    raw_text: Optional[str] = None,
    image_url: Optional[str] = None,
) -> None:
    """Queue a parsed event for moderation.

    Args:
        parsed_event: Parsed event dict from parse_event_with_ai
        parser_name: Name of the parser (kudago, yandex, telegram, etc.)
        raw_text: Optional raw text for display
        image_url: Optional image URL
    """
    settings = get_settings()
    redis = aioredis.from_url(str(settings.redis_url), decode_responses=True)

    try:
        # Build structured form
        form = {
            "title": parsed_event["title"],
            "date_iso": parsed_event["date"].isoformat(),
            "time_24h": parsed_event["time"].strftime("%H:%M") if parsed_event.get("time") else None,
            "venue_name": parsed_event["venue_name"],
            "city": parsed_event.get("city"),
            "address": parsed_event.get("address"),
            "lat": parsed_event.get("lat"),
            "lon": parsed_event.get("lon"),
            "price_min": parsed_event.get("price_min"),
            "price_max": parsed_event.get("price_max"),
            "category": parsed_event["category"],
            "source_url": parsed_event.get("source_url"),
            # Contact info
            "phone": parsed_event.get("phone"),
            "email": parsed_event.get("email"),
            "telegram": parsed_event.get("telegram"),
            "vk": parsed_event.get("vk"),
            "instagram": parsed_event.get("instagram"),
        }

        # Build display text
        if not raw_text:
            contacts = {
                "phone": parsed_event.get("phone"),
                "email": parsed_event.get("email"),
                "telegram": parsed_event.get("telegram"),
                "vk": parsed_event.get("vk"),
                "instagram": parsed_event.get("instagram"),
            }
            contacts_text = format_contacts_for_display(contacts)
            raw_text = f"{parsed_event['title']}\n\n{contacts_text}"

        # Queue payload
        payload = {
            "form": form,
            "raw_text": raw_text,
            "source_url": parsed_event.get("source_url"),
            "image_url": image_url or parsed_event.get("image_url"),
            "source": "parser",
            "parser_name": parser_name,
            "wants_paid_promotion": False,
            "ts": datetime.now().isoformat(),
        }

        # Add to parser queue
        await redis.lpush("ugc:queue:parser", json.dumps(payload, ensure_ascii=False))
        logger.info("ai_parser.enqueued", parser=parser_name, title=parsed_event["title"])

    finally:
        await redis.aclose()
