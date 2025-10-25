"""Migration script to convert all HTML parsers to use AI-based extraction.

This is a template showing the conversion pattern.
Apply this pattern to: afisha_goroda, kassa24
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
import structlog
from selectolax.parser import HTMLParser

from app.ingestors.normalize import clean_text
from app.ingestors.ai_parser_base import parse_event_with_ai, enqueue_parsed_event


logger = structlog.get_logger(module="ing.html_parser")


def extract_event_cards_generic(html: str, selectors: list[str]) -> list[dict[str, Any]]:
    """Generic HTML card extractor for AI processing.

    Args:
        html: Page HTML
        selectors: List of CSS selectors to try for event cards

    Returns:
        List of dicts with 'text' and 'url' keys
    """
    tree = HTMLParser(html)
    items: list[dict[str, Any]] = []

    # Try each selector until we find cards
    for selector in selectors:
        cards = tree.css(selector)
        if cards:
            logger.info("html_parser.found_cards", selector=selector, count=len(cards))
            break
    else:
        logger.warning("html_parser.no_cards_found", tried_selectors=selectors)
        return []

    for card in cards:
        # Extract all text from card
        card_text = clean_text(card.text())
        if not card_text or len(card_text) < 20:
            continue

        # Try to find link
        link = card.css_first("a")
        href = ""
        if link:
            href = link.attributes.get("href", "")

        items.append({
            "text": card_text,
            "url": href,
        })

    return items


async def ingest_generic_html_site(
    html: str,
    city: str,
    parser_name: str,
    base_url: str,
    card_selectors: list[str],
) -> int:
    """Generic ingest function for HTML-based sites using AI parsing.

    Args:
        html: Page HTML
        city: City name
        parser_name: Parser identifier (e.g., 'afisha_goroda')
        base_url: Base URL for relative links
        card_selectors: CSS selectors to try for event cards

    Returns:
        Number of events queued
    """
    # Extract event cards
    cards = extract_event_cards_generic(html, card_selectors)

    if not cards:
        logger.warning("html_parser.no_events", parser=parser_name, city=city)
        return 0

    logger.info("html_parser.parsing_with_ai", parser=parser_name, city=city, total_cards=len(cards))

    # Parse each card with AI
    queued = 0
    for card in cards:
        try:
            # Fix relative URLs
            url = card["url"]
            if url and not url.startswith("http"):
                url = base_url.rstrip("/") + "/" + url.lstrip("/")

            parsed = await parse_event_with_ai(
                text=card["text"],
                source_url=url if url else None,
                source_type=parser_name,
                city=city,
                use_cache=True,
            )

            if not parsed:
                continue

            # Enqueue
            await enqueue_parsed_event(
                parsed_event=parsed,
                parser_name=parser_name,
                raw_text=card["text"],
                image_url=None,
            )

            queued += 1

        except Exception as e:
            logger.error("html_parser.event_error", parser=parser_name, error=str(e))
            continue

    logger.info("html_parser.complete", parser=parser_name, city=city, queued=queued)
    return queued
