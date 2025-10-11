from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class PlaceRecord(BaseModel):
    """Unified place record used by providers and merging.

    Fields are aligned with ORM Place where possible.
    """

    model_config = ConfigDict(extra="ignore")

    id: Optional[str] = None
    name: str
    category: str
    address: str = ""
    lat: float
    lon: float
    phone: Optional[str] = None
    hours: Optional[dict[str, Any]] = None
    rating: Optional[float] = None
    price_level: Optional[int] = None
    source: str
    external_id: str

