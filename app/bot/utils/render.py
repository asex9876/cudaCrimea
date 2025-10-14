from __future__ import annotations

from app.api.schemas import EventOut, PlaceOut
from typing import Any


def render_place_card(p: PlaceOut) -> str:
    parts = [f"{p.name} ({p.category})", p.address]
    if p.rating is not None:
        parts.append(f"Рейтинг: {p.rating:.1f}")
    if p.price_level is not None:
        parts.append(f"Уровень цен: {p.price_level}")
    if getattr(p, "phone", None):
        parts.append(f"Тел.: {getattr(p, 'phone')}" )
    return "\n".join(filter(None, parts))


def _to_text_date(d: Any) -> str:
    try:
        # pydantic date has isoformat()
        return d.isoformat()  # type: ignore[no-any-return]
    except Exception:
        return str(d)


def _get_category_emoji(category: str) -> str:
    """Get emoji for event category."""
    emoji_map = {
        "concert": "🎵",
        "theatre": "🎭",
        "kids": "🎪",
        "tour": "🗺",
        "party": "🎉",
        "expo": "🖼",
        "sport": "⚽",
        "other": "📌",
    }
    return emoji_map.get(category.lower() if category else "", "📌")


def _format_date_ru(date_str: str) -> str:
    """Format date to Russian style (DD месяц)."""
    try:
        from datetime import datetime
        months_ru = {
            1: "января", 2: "февраля", 3: "марта", 4: "апреля",
            5: "мая", 6: "июня", 7: "июля", 8: "августа",
            9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
        }

        # Try to parse ISO format
        if isinstance(date_str, str) and len(date_str) >= 10:
            dt = datetime.fromisoformat(date_str[:10])
            return f"{dt.day} {months_ru[dt.month]}"
        return date_str
    except Exception:
        return date_str


def render_event_card(e: EventOut | Any) -> str:
    """Render event card in modern minimalistic style with emojis.

    Format:
    🎵 **Title**

    📅 DD месяц • HH:MM
    📍 Venue • Address
    💰 Price
    """
    category = getattr(e, "category", "") or "other"
    emoji = _get_category_emoji(category)
    title = getattr(e, "title", "Без названия")

    # Header with category emoji and bold title
    parts = [f"{emoji} <b>{title}</b>", ""]  # Empty line for spacing

    # Date and time line
    date_raw = getattr(e, "date", "")
    date_text = _format_date_ru(_to_text_date(date_raw))
    time_text = getattr(e, "time", None)

    if date_text:
        date_line = f"📅 {date_text}"
        if time_text:
            date_line += f" • {time_text}"
        parts.append(date_line)

    # Location line (venue and address combined)
    venue = getattr(e, "venue_name", "")
    address = getattr(e, "address", "")

    if venue or address:
        location_parts = [venue, address]
        location_text = " • ".join(filter(None, location_parts))
        parts.append(f"📍 {location_text}")

    # Price line
    price_min = getattr(e, "price_min", None)
    price_max = getattr(e, "price_max", None)

    if price_min == 0 and price_max == 0:
        parts.append("💰 Бесплатно")
    elif price_min is not None and price_max is not None and price_min != price_max:
        parts.append(f"💰 {price_min}–{price_max} ₽")
    elif price_min is not None and price_min > 0:
        parts.append(f"💰 от {price_min} ₽")
    elif price_max is not None and price_max > 0:
        parts.append(f"💰 до {price_max} ₽")

    return "\n".join(filter(None, parts))
