"""ORM models for users, events, places, links, ads slots, clicks."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Any, Optional

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    BigInteger,
    Boolean,
    SmallInteger,
    String,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class User(Base):
    """Telegram user profile and preferences."""

    __tablename__ = "users"

    tg_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # BIGINT
    city: Mapped[str] = mapped_column(String)
    home_lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    home_lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    prefs: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb"), default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class Event(Base):
    """Event entity with geo, pricing info and paid placement support."""

    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String)
    date: Mapped[date] = mapped_column(Date)
    time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)

    # Pricing
    price_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # kopecks
    price_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # kopecks
    is_free: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))

    # Location
    category: Mapped[str] = mapped_column(String)
    city: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    venue_name: Mapped[str] = mapped_column(String)
    address: Mapped[str] = mapped_column(String)
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Content
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # Legacy: first photo
    images: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # JSON array of photo URLs

    # Source
    source: Mapped[str] = mapped_column(String)  # 'afisha_goroda', 'ugc', 'manual', 'advertiser'
    source_url: Mapped[str] = mapped_column(String)
    quality_score: Mapped[float] = mapped_column(Float, server_default=text("0"))

    # Paid placement (NEW)
    event_type: Mapped[str] = mapped_column(String, server_default=text("'free'"))  # 'free' | 'paid'
    advertiser_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("advertisers.id", ondelete="SET NULL"), nullable=True
    )
    pricing_model: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # 'fixed', 'cpc', 'cpm'
    price_paid: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # kopecks - amount advertiser paid
    budget: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # kopecks - for CPC/CPM
    spent_budget: Mapped[Optional[int]] = mapped_column(Integer, server_default=text("0"), nullable=True)  # kopecks
    position: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # 'standard', 'top', 'pinned'

    # Analytics
    views: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    clicks: Mapped[int] = mapped_column(Integer, server_default=text("0"))

    # Status
    status: Mapped[str] = mapped_column(String, server_default=text("'active'"))  # 'draft', 'active', 'past', 'pending_moderation'
    is_approved: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))

    # Deduplication
    duplicate_of: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "category IN ('concert','theatre','kids','tour','party','expo','other')",
            name="ck_events_category",
        ),
        CheckConstraint(
            "event_type IN ('free','paid')",
            name="ck_events_type",
        ),
        CheckConstraint(
            "pricing_model IS NULL OR pricing_model IN ('fixed','cpc','cpm')",
            name="ck_events_pricing_model",
        ),
        CheckConstraint(
            "position IS NULL OR position IN ('standard','top','pinned')",
            name="ck_events_position",
        ),
        CheckConstraint(
            "status IN ('draft','active','past','pending_moderation')",
            name="ck_events_status",
        ),
        Index("ix_events_date", "date"),
        Index("ix_events_category", "category"),
        Index("ix_events_lat_lon", "lat", "lon"),
        Index("ix_events_type_status", "event_type", "status"),
    )


class Place(Base):
    """Place of interest with geo and metadata."""

    __tablename__ = "places"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String)
    category: Mapped[str] = mapped_column(String)
    address: Mapped[str] = mapped_column(String)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    hours: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_level: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    source: Mapped[str] = mapped_column(String)
    external_id: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    image_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "category IN ('cafe','bar','restaurant','dessert','coffee','other')",
            name="ck_places_category",
        ),
        Index("ix_places_lat_lon", "lat", "lon"),
    )


class Advertiser(Base):
    """Advertisers (companies that pay for event placement)."""

    __tablename__ = "advertisers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String)  # Company name
    contact_person: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    email: Mapped[str] = mapped_column(String)
    phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # Owner's notes
    balance: Mapped[int] = mapped_column(Integer, server_default=text("0"))  # kopecks - prepaid balance
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    __table_args__ = (
        Index("ix_advertisers_email", "email"),
    )


class PlacementRequest(Base):
    """Paid placement requests from advertisers."""

    __tablename__ = "placement_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    advertiser_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("advertisers.id", ondelete="CASCADE")
    )
    event_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="SET NULL"), nullable=True
    )

    # Event data (before approval)
    event_title: Mapped[str] = mapped_column(String)
    event_date: Mapped[date] = mapped_column(Date)
    event_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    event_description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    event_venue: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    event_address: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Placement terms
    pricing_model: Mapped[str] = mapped_column(String)  # 'fixed', 'cpc', 'cpm'
    position: Mapped[str] = mapped_column(String, server_default=text("'standard'"))  # 'standard', 'top', 'pinned'
    budget: Mapped[int] = mapped_column(Integer)  # kopecks
    price_per_unit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # for CPC/CPM (kopecks)

    # Status workflow
    status: Mapped[str] = mapped_column(String, server_default=text("'pending'"))
    # 'pending' -> 'approved' -> 'paid' -> 'active' -> 'completed' | 'rejected'
    reject_reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Payment
    invoice_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "pricing_model IN ('fixed','cpc','cpm')",
            name="ck_placement_pricing_model",
        ),
        CheckConstraint(
            "position IN ('standard','top','pinned')",
            name="ck_placement_position",
        ),
        CheckConstraint(
            "status IN ('pending','approved','rejected','paid','active','completed')",
            name="ck_placement_status",
        ),
        Index("ix_placement_requests_status", "status"),
        Index("ix_placement_requests_advertiser", "advertiser_id"),
    )


class AdInteraction(Base):
    """Track views and clicks for CPC/CPM ads."""

    __tablename__ = "ad_interactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE")
    )
    user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)  # tg_id (can be anonymous)
    interaction_type: Mapped[str] = mapped_column(String)  # 'view' | 'click'
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "interaction_type IN ('view','click')",
            name="ck_ad_interactions_type",
        ),
        Index("ix_ad_interactions_event", "event_id", "created_at"),
        Index("ix_ad_interactions_type", "interaction_type"),
    )


class UGCSubmission(Base):
    """User-generated content submissions for moderation."""

    __tablename__ = "ugc_submissions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(BigInteger)  # tg_id
    raw_text: Mapped[str] = mapped_column(String)
    images: Mapped[Optional[list[str]]] = mapped_column(JSONB, nullable=True)  # array of URLs
    source_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # LLM extraction results
    extracted_data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    # Moderation
    status: Mapped[str] = mapped_column(String, server_default=text("'pending'"))
    # 'pending', 'approved', 'rejected', 'auto_approved'
    reject_reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    event_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    moderated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','approved','rejected','auto_approved')",
            name="ck_ugc_status",
        ),
        Index("ix_ugc_submissions_status", "status"),
        Index("ix_ugc_submissions_user", "user_id"),
    )


class EditorialPin(Base):
    """Editorial pin to feature an event or place with scheduling and priority."""

    __tablename__ = "editorial_pins"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_type: Mapped[str] = mapped_column(String)  # 'event' | 'place'
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    title_override: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    city: Mapped[str] = mapped_column(String)
    active_from: Mapped[date] = mapped_column(Date)
    active_to: Mapped[date] = mapped_column(Date)
    priority: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))

    __table_args__ = (
        CheckConstraint("item_type IN ('event','place')", name="ck_pins_item_type"),
        Index("ix_pins_city_date", "city", "active_from", "active_to"),
    )


class CuratedCard(Base):
    """Generic card entity to present curated choices to users.

    Can reference an event/place or be standalone external link.
    """

    __tablename__ = "curated_cards"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_type: Mapped[str] = mapped_column(String)  # 'event' | 'place' | 'external'
    ref_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    title: Mapped[str] = mapped_column(String)
    subtitle: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    button_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    active_from: Mapped[date] = mapped_column(Date)
    active_to: Mapped[date] = mapped_column(Date)
    priority: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))

    __table_args__ = (
        CheckConstraint("item_type IN ('event','place','external')", name="ck_cards_item_type"),
        Index("ix_cards_city_date", "city", "active_from", "active_to"),
    )


class EventImage(Base):
    """Additional images for events (gallery)."""

    __tablename__ = "event_images"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(String)
    priority: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))

    __table_args__ = (
        Index("ix_event_images_event_prio", "event_id", "priority"),
    )


class ScheduledPost(Base):
    """Scheduled Telegram post for an event."""

    __tablename__ = "scheduled_posts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"))
    channel: Mapped[str] = mapped_column(String)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String, server_default=text("'scheduled'"))
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"), default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    __table_args__ = (
        CheckConstraint("status IN ('scheduled','sent','cancelled','error')", name="ck_scheduled_posts_status"),
        Index("ix_scheduled_posts_run_at", "run_at"),
    )


class NotificationSettings(Base):
    """Notification channels for admin users."""

    __tablename__ = "notification_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    admin_login: Mapped[str] = mapped_column(String)
    email: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    telegram_chat_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    preferences: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"), default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    __table_args__ = (
        UniqueConstraint("admin_login", name="uq_notification_settings_admin"),
    )


class LLMUsage(Base):
    """LLM/AI token usage tracking for cost analysis."""

    __tablename__ = "llm_usage"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service: Mapped[str] = mapped_column(String)  # extractor, classifier, summarizer, etc
    model: Mapped[str] = mapped_column(String)  # gpt-4o-mini, claude-3-7-sonnet, etc
    provider: Mapped[str] = mapped_column(String, server_default=text("'ai-mediator'"))  # ai-mediator, openai, etc
    prompt_tokens: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    completion_tokens: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    total_tokens: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    cost_rub: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Cost in rubles
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"), default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    __table_args__ = (
        Index("ix_llm_usage_service_date", "service", "created_at"),
        Index("ix_llm_usage_model_date", "model", "created_at"),
        Index("ix_llm_usage_date", "created_at"),
    )


class BotSettings(Base):
    """Bot configuration (avatar, description, commands, etc)."""

    __tablename__ = "bot_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)  # Singleton
    bot_name: Mapped[str] = mapped_column(String, server_default=text("'CudaCrimea Bot'"))
    bot_username: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # Short description
    about: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # Full about text
    avatar_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # Path to uploaded avatar
    welcome_message: Mapped[str] = mapped_column(
        String,
        server_default=text("'Привет! Я помогу найти, куда пойти в Крыму/Севастополе. Выберите город:'")
    )
    commands: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        server_default=text("'[{\"command\":\"start\",\"description\":\"Старт / выбор города\"},{\"command\":\"menu\",\"description\":\"Показать меню\"}]'::jsonb"),
        default=lambda: [
            {"command": "start", "description": "Старт / выбор города"},
            {"command": "menu", "description": "Показать меню"},
        ]
    )
    menu_buttons: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        server_default=text("'[{\"text\":\"🎤 Куда сходить\",\"action\":\"what_to_do\"},{\"text\":\"🍽 Где поесть\",\"action\":\"food\"},{\"text\":\"✍ Предложить событие\",\"action\":\"ugc\"}]'::jsonb"),
        default=lambda: [
            {"text": "🎤 Куда сходить", "action": "what_to_do"},
            {"text": "🍽 Где поесть", "action": "food"},
            {"text": "✍ Предложить событие", "action": "ugc"},
        ]
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint("id = 1", name="ck_bot_settings_singleton"),
    )


class ParsedMessage(Base):
    """Track parsed Telegram messages to avoid duplicates."""

    __tablename__ = "parsed_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_username: Mapped[str] = mapped_column(String)  # Channel username (e.g., "simferopol_afisha")
    message_id: Mapped[int] = mapped_column(BigInteger)  # Telegram message ID
    parsed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    event_created: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))  # Was event created from this message
    event_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("channel_username", "message_id", name="uq_parsed_messages_channel_msg"),
        Index("ix_parsed_messages_channel", "channel_username"),
        Index("ix_parsed_messages_parsed_at", "parsed_at"),
    )
