"""Pydantic DTO schemas for API responses."""

from __future__ import annotations

from datetime import date
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EventOut(BaseModel):
    """Event response model."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    date: date
    time: Optional[str] = None
    price_min: Optional[int] = None
    price_max: Optional[int] = None
    is_free: bool = False
    category: str
    venue_name: str
    address: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    description: Optional[str] = None
    source: str
    source_url: str
    quality_score: float = 0

    # Paid placement info
    event_type: str = "free"  # 'free' | 'paid'
    pricing_model: Optional[str] = None  # 'fixed', 'cpc', 'cpm'
    position: Optional[str] = None  # 'standard', 'top', 'pinned'

    # Analytics (for admin/advertiser)
    views: int = 0
    clicks: int = 0

    # UI helpers
    deeplink: Optional[str] = None
    buttons: list[dict[str, str]] = Field(default_factory=list)
    image_url: Optional[str] = None
    is_ad: bool = False  # Computed field: True if event_type=='paid'


class PlaceOut(BaseModel):
    """Place response model."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    category: str
    address: str
    lat: float
    lon: float
    phone: Optional[str] = None
    hours: Optional[dict[str, Any]] = None
    rating: Optional[float] = None
    price_level: Optional[int] = None
    source: str
    external_id: str
    deeplink: Optional[str] = None
    buttons: list[dict[str, str]] = Field(default_factory=list)
    image_url: Optional[str] = None


class SearchResponse(BaseModel):
    """Combined search response for events and places."""

    events: list[EventOut] = Field(default_factory=list)
    places: list[PlaceOut] = Field(default_factory=list)
    count: int = 0


# New schemas for paid placements

class AdvertiserOut(BaseModel):
    """Advertiser response model."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    contact_person: Optional[str] = None
    email: str
    phone: Optional[str] = None
    balance: int = 0  # kopecks


class AdvertiserCreate(BaseModel):
    """Create advertiser request."""

    name: str = Field(min_length=1, max_length=255)
    contact_person: Optional[str] = None
    email: str = Field(pattern=r'^[\w\.-]+@[\w\.-]+\.\w+$')
    phone: Optional[str] = None
    notes: Optional[str] = None


class PlacementRequestOut(BaseModel):
    """Placement request response model."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    advertiser_id: UUID
    event_id: Optional[UUID] = None
    event_title: str
    event_date: date
    pricing_model: str
    position: str
    budget: int  # kopecks
    status: str
    created_at: Any  # datetime


class PlacementRequestCreate(BaseModel):
    """Create placement request."""

    advertiser_id: UUID
    event_title: str = Field(min_length=1)
    event_date: date
    event_time: Optional[str] = None
    event_description: Optional[str] = None
    event_venue: Optional[str] = None
    event_address: Optional[str] = None
    pricing_model: str = Field(pattern='^(fixed|cpc|cpm)$')
    position: str = Field(default='standard', pattern='^(standard|top|pinned)$')
    budget: int = Field(gt=0)  # kopecks
    price_per_unit: Optional[int] = None  # for CPC/CPM


class UGCSubmissionOut(BaseModel):
    """UGC submission response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: int
    raw_text: str
    status: str
    extracted_data: Optional[dict[str, Any]] = None
    created_at: Any  # datetime
