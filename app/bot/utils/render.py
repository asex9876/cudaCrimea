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


def render_event_card(e: EventOut | Any) -> str:
    date_text = _to_text_date(getattr(e, "date", ""))
    time_text = getattr(e, "time", None) or ""
    parts = [
        f"{getattr(e, 'title', '')} ({getattr(e, 'category', '')})",
        (date_text + (f" {time_text}" if time_text else "")).strip(),
        getattr(e, "venue_name", ""),
        getattr(e, "address", ""),
    ]
    if e.price_min is not None and e.price_max is not None:
        parts.append(f"Цена: {e.price_min}–{e.price_max} ₽")
    elif e.price_min is not None:
        parts.append(f"Цена от {e.price_min} ₽")
    return "\n".join(filter(None, parts))
