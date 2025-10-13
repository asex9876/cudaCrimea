"""Event field extractor using an OpenAI-compatible API.

The model is prompted to return strict JSON which is validated by Pydantic.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

import structlog
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.core.config import get_settings
from app.core.llm import client as llm_client


logger = structlog.get_logger(module="llm.extractor")


class EventDraft(BaseModel):
    """Draft event payload parsed from free text.

    Attributes:
        title: Title of the event.
        date_iso: ISO date string YYYY-MM-DD.
        time_24h: 24-hour time HH:MM, optional.
        venue_name: Venue name.
        address: Venue address.
        price_min: Minimal price in currency units.
        price_max: Maximal price.
        category: One of allowed categories.
        source_url: Optional source URL.
    """

    model_config = ConfigDict(extra="ignore")

    title: Optional[str] = None
    date_iso: Optional[str] = None
    time_24h: Optional[str] = None
    venue_name: Optional[str] = None
    address: Optional[str] = None
    price_min: Optional[int] = None
    price_max: Optional[int] = None
    category: Optional[str] = Field(default=None)
    source_url: Optional[str] = None

    @field_validator("date_iso")
    @classmethod
    def _validate_date(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        # Accept both YYYY-MM-DD and ISO 8601 with time (extract date part)
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            return v
        # If it's ISO 8601 with time component, extract date
        match = re.match(r"(\d{4}-\d{2}-\d{2})T", v)
        if match:
            return match.group(1)
        raise ValueError("date_iso must be YYYY-MM-DD or ISO 8601 datetime")

    @field_validator("time_24h")
    @classmethod
    def _validate_time(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        if re.fullmatch(r"\d{2}:\d{2}", v):
            hh, mm = v.split(":", 1)
            if 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59:
                return v
        raise ValueError("time_24h must be HH:MM in 24h")

    @field_validator("category")
    @classmethod
    def _validate_category(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        allowed = {"concert", "theatre", "kids", "tour", "party", "expo", "other"}
        vl = v.lower()
        if vl in allowed:
            return vl
        raise ValueError("invalid category")


SYS_PROMPT = (
    "Ты — извлекатель фактов о событиях в Крыму/Севастополе. "
    "Верни JSON: {title, date_iso, time_24h|null, venue_name, address, price_min, price_max, "
    "category in [concert|theatre|kids|tour|party|expo|other], source_url}. "
    "Если нет данных — null. Не придумывай."
)

def extract_event_fields(text: str, source_url: Optional[str] = None) -> EventDraft:
    """Extract structured event fields from raw text using LLM.

    Args:
        text: Raw text content.
        source_url: Optional associated URL.

    Returns:
        EventDraft: Validated event draft model.
    """

    s = get_settings()
    model = s.openai_model_extractor
    msg = [
        {"role": "system", "content": SYS_PROMPT},
        {"role": "user", "content": text if not source_url else f"SOURCE: {source_url}\n\n{text}"},
    ]
    content = llm_client.chat_complete(model=model, messages=msg, temperature=0.0)
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        # Try to extract JSON substring
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            data = json.loads(content[start : end + 1])
        else:
            raise

    if source_url and not data.get("source_url"):
        data["source_url"] = source_url

    try:
        return EventDraft.model_validate(data)
    except ValidationError as e:
        logger.warning("llm.extractor.validation_failed", errors=e.errors())
        # Return partial best-effort result with None for invalid fields
        cleaned: dict[str, Any] = {k: data.get(k) for k in (
            "title",
            "date_iso",
            "time_24h",
            "venue_name",
            "address",
            "price_min",
            "price_max",
            "category",
            "source_url",
        )}
        return EventDraft.model_validate(cleaned)
