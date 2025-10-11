"""Yandex Afisha ingestor for Sevastopol/Simferopol."""

from __future__ import annotations

from datetime import date
from typing import Any, Iterable, Optional

import structlog
from selectolax.parser import HTMLParser
from playwright.async_api import async_playwright
from tenacity import AsyncRetrying, retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from app.core.services.quality import source_weight
from app.db.dao.events import upsert_event
from app.ingestors.normalize import clean_text, dedup_events, parse_date, parse_time


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


def parse_list(html: str) -> list[dict[str, Any]]:
    tree = HTMLParser(html)
    items: list[dict[str, Any]] = []
    # Generic selectors; may need adjustments if markup changes
    for node in tree.css("a\[href\][data-event-id], a.Link\[href\]"):
        href = node.attributes.get("href", "")
        title_node = node.css_first("h3, h2, .EventTitle__title")
        if not title_node:
            continue
        title = clean_text(title_node.text())
        date_node = node.css_first("time")
        date_str = clean_text(date_node.text()) if date_node else ""
        time_node = node.css_first(".event-time, time .time")
        time_str = clean_text(time_node.text()) if time_node else ""
        venue_node = node.css_first(".place, .EventVenue__name, .event-place")
        venue = clean_text(venue_node.text()) if venue_node else ""
        addr_node = node.css_first(".address, .EventVenue__address")
        addr = clean_text(addr_node.text()) if addr_node else None
        price_node = node.css_first(".price, .EventPrice__price")
        price_s = clean_text(price_node.text()) if price_node else ""
        price_min = None
        for tok in price_s.replace("₽", " ").split():
            if tok.isdigit():
                price_min = int(tok)
                break
        items.append(
            {
                "title": title,
                "date": parse_date(date_str) or date.today(),
                "time": parse_time(time_str),
                "venue_name": venue or "",
                "address": addr,
                "price_min": price_min,
                "href": href if href.startswith("http") else f"https://afisha.yandex.ru{href}",
            }
        )
    return items


async def ingest(city: str, session) -> int:
    """Fetch, parse, normalize and save events for a city.

    Returns number of upserts.
    """

    html = None
    async for attempt in AsyncRetrying(stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=1, max=10)):
        with attempt:
            html = await fetch_events_html(city)
    assert html is not None
    rows = parse_list(html)
    rows = dedup_events(rows)
    cnt = 0
    for r in rows:
        ev = await upsert_event(
            session,
            title=r["title"],
            date_=r["date"],
            time_=r.get("time"),
            city=city,
            venue_name=r.get("venue_name", ""),
            address=r.get("address"),
            lat=None,
            lon=None,
            price_min=r.get("price_min"),
            price_max=None,
            category="concert",
            source="yandex",
            source_url=r.get("href", ""),
            quality_base=source_weight("yandex"),
        )
        cnt += 1
    await session.commit()
    logger.info("ingest.yandex.saved", city=city, count=cnt)
    return cnt

