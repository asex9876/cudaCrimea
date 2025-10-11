"""Normalization helpers for ingested data."""

from __future__ import annotations

from datetime import date, time
from typing import Any, Iterable, Mapping, Optional

import dateparser  # type: ignore[import-untyped]
from rapidfuzz import fuzz


def clean_text(text: str) -> str:
    s = " ".join((text or "").split())
    return s.strip()


def parse_date(date_str: str) -> Optional[date]:
    if not date_str:
        return None
    dt = dateparser.parse(date_str)
    return dt.date() if dt else None


def parse_time(time_str: str | None) -> Optional[time]:
    if not time_str:
        return None
    dt = dateparser.parse(time_str)
    return dt.time() if dt else None


def dedup_events(items: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate by normalized (title+date+venue) with fuzzy match.

    Items must have keys: title, date, venue_name.
    """

    seen: list[dict[str, Any]] = []
    for it in items:
        title = clean_text(str(it.get("title", ""))).lower()
        date_s = str(it.get("date", ""))
        venue = clean_text(str(it.get("venue_name", ""))).lower()
        dup = False
        for ex in seen:
            score = fuzz.token_set_ratio(title, ex["_title"])  # type: ignore[index]
            if score >= 90 and ex["_date"] == date_s and fuzz.partial_ratio(venue, ex["_venue"]) >= 90:  # type: ignore[index]
                dup = True
                break
        if not dup:
            d = dict(it)
            d["_title"] = title
            d["_date"] = date_s
            d["_venue"] = venue
            seen.append(d)
    for d in seen:
        d.pop("_title", None)
        d.pop("_date", None)
        d.pop("_venue", None)
    return seen

