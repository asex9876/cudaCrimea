"""Yandex Afisha ingestor for Sevastopol/Simferopol.

Now uses AI-based extraction for accurate parsing instead of HTML selectors.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable, Optional
import json

import structlog
from selectolax.parser import HTMLParser
from playwright.async_api import async_playwright
from tenacity import AsyncRetrying, retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from app.core.services.quality import source_weight
from app.db.dao.events import upsert_event
from app.ingestors.normalize import clean_text, dedup_events, parse_date, parse_time
from app.ingestors.ai_parser_base import parse_event_with_ai, enqueue_parsed_event


logger = structlog.get_logger(module="ing.yandex_afisha")

CITY_PATHS = {
    "севастополь": "sevastopol",
    "симферополь": "simferopol",
}


def _url(city: str) -> str:
    slug = CITY_PATHS.get(city.strip().lower())
    if not slug:
        raise ValueError(f"unsupported city for yandex afisha: {city}")
    return f"https://afisha.yandex.ru/{slug}"


async def fetch_events_html(city: str) -> str:
    url = _url(city)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)
        html = await page.content()
        await browser.close()
    return html


def extract_event_nodes(html: str) -> list[dict[str, Any]]:
    """Extract raw event card data from HTML for AI processing.

    Instead of parsing specific fields, we extract complete event cards
    with all their text content for AI to analyze.
    """
    tree = HTMLParser(html)
    items: list[dict[str, Any]] = []

    # Generic selectors for event cards
    for node in tree.css("a[href][data-event-id], a.Link[href]"):
        href = node.attributes.get("href", "")
        if not href:
            continue

        # Extract all text from the card
        card_text = clean_text(node.text())
        if not card_text or len(card_text) < 20:
            continue

        # Get full URL
        full_url = href if href.startswith("http") else f"https://afisha.yandex.ru{href}"

        items.append({
            "text": card_text,
            "url": full_url,
        })

    logger.info("yandex.extracted_cards", count=len(items))
    return items


async def ingest(city: str, session) -> int:
    """Fetch, parse with AI, and queue events for a city.

    Returns number of events queued.
    """

    html = None
    async for attempt in AsyncRetrying(stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=1, max=10)):
        with attempt:
            html = await fetch_events_html(city)
    assert html is not None

    # Extract event cards
    event_cards = extract_event_nodes(html)

    if not event_cards:
        logger.warning("yandex.no_events_found", city=city)
        return 0

    logger.info("yandex.parsing_with_ai", city=city, total_cards=len(event_cards))

    # Parse each event with AI
    queued = 0
    for card in event_cards:
        try:
            parsed = await parse_event_with_ai(
                text=card["text"],
                source_url=card["url"],
                source_type="yandex_afisha",
                city=city,
                use_cache=True,
            )

            if not parsed:
                continue

            # Enqueue the parsed event
            await enqueue_parsed_event(
                parsed_event=parsed,
                parser_name="yandex_afisha",
                raw_text=card["text"],
                image_url=None,
            )

            queued += 1

        except Exception as e:
            logger.error("yandex.event_process_error", url=card["url"], error=str(e))
            continue

    logger.info("yandex.import_complete", city=city, total=len(event_cards), queued=queued)
    return queued

