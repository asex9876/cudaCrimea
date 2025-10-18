"""Kassa24 events ingestor for Sevastopol.

Now uses AI-based extraction for accurate parsing.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import structlog
from playwright.async_api import async_playwright
from selectolax.parser import HTMLParser
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential_jitter

from app.core.services.quality import source_weight
from app.db.dao.events import upsert_event
from app.ingestors.normalize import clean_text, dedup_events, parse_date, parse_time
from app.ingestors.migrate_html_parsers import ingest_generic_html_site


logger = structlog.get_logger(module="ing.kassa24")


URL = "https://kassa24.ru/sevastopol/events"  # example listing URL


async def fetch_html() -> str:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)
        html = await page.content()
        await browser.close()
    return html


def parse_list(html: str) -> list[dict[str, Any]]:
    tree = HTMLParser(html)
    items: list[dict[str, Any]] = []
    for card in tree.css(".event-card, article, .item"):
        title_node = card.css_first(".title, h3, h2, a")
        date_node = card.css_first("time, .date")
        time_node = card.css_first(".time")
        venue_node = card.css_first(".place, .venue")
        price_node = card.css_first(".price")
        link_node = card.css_first("a")
        if not title_node or not link_node:
            continue
        href = link_node.attributes.get("href", "")
        title = clean_text(title_node.text())
        date_str = clean_text(date_node.text()) if date_node else ""
        time_str = clean_text(time_node.text()) if time_node else ""
        venue = clean_text(venue_node.text()) if venue_node else ""
        price = None
        price_s = clean_text(price_node.text()) if price_node else ""
        for tok in price_s.replace("₽", " ").split():
            if tok.isdigit():
                price = int(tok)
                break
        items.append(
            {
                "title": title,
                "date": parse_date(date_str) or date.today(),
                "time": parse_time(time_str),
                "venue_name": venue,
                "price_min": price,
                "href": href,
            }
        )
    return items


async def ingest(session) -> int:
    """Fetch and parse events using AI."""
    html = None
    async for _ in AsyncRetrying(stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=1, max=10)):
        html = await fetch_html()
    assert html is not None

    # Use AI-based parsing
    queued = await ingest_generic_html_site(
        html=html,
        city="Севастополь",
        parser_name="kassa24",
        base_url="https://kassa24.ru",
        card_selectors=[".event-card", "article", ".item"],
    )

    logger.info("kassa24.complete", queued=queued)
    return queued

