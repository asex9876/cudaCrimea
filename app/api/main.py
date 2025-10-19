"""FastAPI application entrypoint with search and utility endpoints.

Run locally:
    uvicorn app.api.main:app --reload
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import date, datetime, time as dtime, timedelta
import math
import json
from typing import Any, Iterable, Mapping, Optional

import structlog
from fastapi import Body, Depends, FastAPI, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from redis import asyncio as aioredis
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import EventOut, PlaceOut, SearchResponse, AdvertiserOut, PlacementRequestOut
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.services.geo import distance_km, two_gis_deeplink, yandex_deeplink
from app.core.services.ranking import score_event, score_place
from app.core.services.monetization import MonetizationService, PlacementType
from app.db.models import Event, Place, AdInteraction, UGCSubmission, EditorialPin, CuratedCard
from app.db.session import get_session
from prometheus_fastapi_instrumentator import Instrumentator
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.redis import RedisIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from app.admin.main import app as admin_app
from app.core import runtime_config


settings = get_settings()
setup_logging(settings.log_level)
logger = structlog.get_logger(module="api")

app = FastAPI(title=f"{settings.app_name} — API")
app.mount("/admin", admin_app)

# Initialize Sentry and Prometheus BEFORE startup to avoid middleware errors
if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            SqlalchemyIntegration(),
            RedisIntegration(),
            LoggingIntegration(level=None, event_level=None),
        ],
        traces_sample_rate=0.2,
        environment=settings.env,
    )

# Expose Prometheus metrics
Instrumentator().instrument(app).expose(app)

CACHE_TTL = 300
_redis: aioredis.Redis | None = None


def get_city_center(city: str) -> Optional[tuple[float, float]]:
    centers: dict[str, tuple[float, float]] = {
        "симферополь": (44.9521, 34.1024),
        "севастополь": (44.6167, 33.5254),
        "ялта": (44.4987, 34.1668),
        "евпатория": (45.1904, 33.3669),
        "феодосия": (45.0319, 35.3824),
        "керчь": (45.3568, 36.4675),
        "алушта": (44.6764, 34.4100),
        "судак": (44.8500, 34.9833),
    }
    return centers.get(city.strip().lower())


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(str(settings.redis_url), decode_responses=True)
    return _redis


@app.on_event("startup")
async def on_startup() -> None:
    logger.info("api.startup", env=settings.env)
    # Load runtime overrides (admin settings)
    runtime_config.load_from_file()
    # Warm up redis connection
    await get_redis()
    # Place for potential warm-ups (DB, caches)


@app.on_event("shutdown")
async def on_shutdown() -> None:
    logger.info("api.shutdown")
    if _redis is not None:
        await _redis.close()


@app.get("/")
async def root() -> dict[str, str]:
    """API root endpoint"""
    return {"message": "cudaCrimea API", "admin": "/admin/", "health": "/api/health"}


# --------- Schemas ---------


class WhenEnum(str):
    TODAY = "today"
    TONIGHT = "tonight"
    WEEKEND = "weekend"
    DATE = "date"


class SearchParams(BaseModel):
    city: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    when: str = Field(pattern="^(hot|today|tonight|tomorrow|weekend|this_week|this_month|date)$")
    date: Optional[date] = None
    budget_max: Optional[int] = None
    categories: Optional[list[str]] = None


class PollCreateIn(BaseModel):
    city: str
    when: str = Field(pattern="^(hot|today|tonight|tomorrow|weekend|this_week|this_month|date)$")
    budget_max: Optional[int] = None
    lat: Optional[float] = None
    lon: Optional[float] = None


class PollItemOut(BaseModel):
    title: str
    subtitle: str
    button_url: str


class UGCIn(BaseModel):
    raw_text: str
    source_url: Optional[str] = None
    images: Optional[list[str]] = None
    form: Optional[dict[str, Any]] = None
    user_id: Optional[int] = None
    wants_paid_promotion: Optional[bool] = False


class PlacementPriceRequest(BaseModel):
    """Request to calculate placement price."""
    placement_type: str = Field(..., pattern="^(broadcast_all|broadcast_city|broadcast_zone|hot)$")
    event_datetime: datetime
    target_city: Optional[str] = None
    target_zone: Optional[str] = None


class PlacementPriceResponse(BaseModel):
    """Response with calculated placement price."""
    price: float
    cost_per_lead: float
    audience_size: int
    conversion_rate: float
    time_coefficient: float
    breakdown: str


class MonetizationSettingUpdate(BaseModel):
    """Update a monetization setting."""
    setting_key: str
    setting_value: float
    updated_by: Optional[str] = None


# --------- Helpers ---------


def _date_filter_for_when(when: str, req_date: Optional[date], now: datetime) -> tuple[list[date], Optional[dtime], Optional[dtime]]:
    """Generate date range and time filter based on 'when' parameter.

    Args:
        when: Time selector (hot, today, tonight, tomorrow, weekend, this_week, this_month, date)
        req_date: Specific date when when='date'
        now: Current datetime

    Returns:
        Tuple of (list of dates, optional time_from filter, optional time_to filter)
    """
    today = now.date()
    tomorrow = today + timedelta(days=1)
    current_time = now.time()

    if when == "hot":
        # Hot events: from current time until 8:00 AM next day
        # Includes both today's events (from now) and tomorrow's early events (until 8:00 AM)
        time_from = dtime(hour=now.hour, minute=0)
        time_to = dtime(hour=8, minute=0)
        return [today, tomorrow], time_from, time_to

    if when == "today":
        return [today], None, None

    if when == "tonight":
        return [today], dtime(hour=17, minute=0), None

    if when == "tomorrow":
        return [tomorrow], None, None

    if when == "weekend":
        # Find upcoming Saturday and Sunday
        days_ahead = (5 - today.weekday()) % 7  # Saturday index 5
        if days_ahead == 0 and today.weekday() == 5:  # If today is Saturday
            saturday = today
        else:
            saturday = today + timedelta(days=days_ahead if days_ahead > 0 else 7)
        sunday = saturday + timedelta(days=1)
        return [saturday, sunday], None, None

    if when == "this_week":
        # From today until Sunday
        days_until_sunday = (6 - today.weekday()) % 7
        if days_until_sunday == 0:  # If today is Sunday
            end_date = today
        else:
            end_date = today + timedelta(days=days_until_sunday)
        dates = [today + timedelta(days=i) for i in range((end_date - today).days + 1)]
        return dates, None, None

    if when == "this_month":
        # Rest of current month
        import calendar
        last_day = calendar.monthrange(today.year, today.month)[1]
        end_date = date(today.year, today.month, last_day)
        dates = [today + timedelta(days=i) for i in range((end_date - today).days + 1)]
        return dates, None, None

    if when == "date" and req_date is not None:
        return [req_date], None, None

    return [today], None, None


def _bbox(lat: float, lon: float, km: float) -> tuple[float, float, float, float]:
    # Rough approximation: 1 deg lat ~111 km, lon scaled by cos(lat)
    dlat = km / 111.0
    dlon = km / (111.0 * max(0.1, abs(math.cos(lat * math.pi / 180))))
    return lat - dlat, lat + dlat, lon - dlon, lon + dlon


def _buttons_for_event(e: Mapping[str, Any]) -> list[dict[str, str]]:
    btns: list[dict[str, str]] = []
    src = str(e.get("source_url") or "").strip()
    if src:
        btns.append({"type": "site", "url": src})
        # Consider same url as booking when price info exists
        if e.get("price_min") is not None or e.get("price_max") is not None:
            btns.append({"type": "book", "url": src})
    return btns


def _buttons_for_place(p: Mapping[str, Any]) -> list[dict[str, str]]:
    btns: list[dict[str, str]] = []
    phone = str(p.get("phone") or "").strip()
    if phone:
        btns.append({"type": "call", "url": f"tel:{phone}"})
    return btns


def _prefs_from_query(budget_max: Optional[int], categories: Optional[list[str]]) -> dict[str, Any]:
    prefs: dict[str, Any] = {}
    if budget_max is not None:
        prefs["budget_max"] = budget_max
    if categories:
        prefs["event_categories"] = categories
        prefs["place_categories"] = categories
    return prefs


# --------- Routes ---------


@app.get("/api/health")
async def health() -> dict[str, bool]:
    """Liveness probe.

    Returns:
        {"ok": true}
    """

    return {"ok": True}


@app.get("/api/search", response_model=SearchResponse)
async def search(
    city: str = Query(..., min_length=1),
    when: str = Query("today", pattern="^(hot|today|tonight|tomorrow|weekend|this_week|this_month|date)$"),
    date_q: Optional[date] = Query(None, alias="date"),
    lat: Optional[float] = Query(None),
    lon: Optional[float] = Query(None),
    budget_max: Optional[int] = Query(None, ge=0),
    categories: Optional[list[str]] = Query(None),
    session: AsyncSession = Depends(get_session),
) -> SearchResponse:
    """Search events and places with scoring and caching.

    Args:
        city: City name.
        when: Time window selector.
        date_q: Specific date when `when=date`.
        lat: Optional latitude for proximity search.
        lon: Optional longitude for proximity search.
        budget_max: Optional budget cap.
        categories: Optional list of categories to filter.
        session: DB session dependency.

    Returns:
        SearchResponse with events, places, and ads.
    """

    now = datetime.utcnow()
    params = SearchParams(
        city=city,
        when=when,
        date=date_q,
        lat=lat,
        lon=lon,
        budget_max=budget_max,
        categories=categories,
    )
    prefs = _prefs_from_query(budget_max, categories)
    user_ctx = {"home_lat": lat, "home_lon": lon, "prefs": prefs}

    # Cache lookup
    redis = await get_redis()
    cache_key = "search:" + json.dumps(
        {
            "city": params.city.lower(),
            "when": params.when,
            "date": params.date.isoformat() if params.date else None,
            "lat": round(params.lat or 0.0, 4),
            "lon": round(params.lon or 0.0, 4),
            "budget_max": params.budget_max,
            "categories": sorted(params.categories or []),
        },
        sort_keys=True,
        ensure_ascii=False,
    )

    cached = await redis.get(cache_key)
    if cached:
        logger.info("search.cache.hit", key=cache_key)
        return SearchResponse.model_validate_json(cached)

    logger.info("search.request", city=city, when=when, has_geo=lat is not None and lon is not None)

    # Build date filter
    dates, time_from, time_to = _date_filter_for_when(when, date_q, now)

    # Determine center for city if no lat/lon provided
    center = None
    if lat is not None and lon is not None:
        center = (lat, lon)
    else:
        center = get_city_center(city)

    # Query Events candidates
    event_stmt = select(Event)
    # Фильтруем только активные события (не прошедшие)
    event_stmt = event_stmt.where(Event.status == "active")
    event_stmt = event_stmt.where(Event.date.in_(dates))

    # Special logic for "hot" events (today from time_from, tomorrow until time_to)
    if when == "hot" and time_from is not None and time_to is not None:
        today = now.date()
        tomorrow = today + timedelta(days=1)
        # (date == today AND time >= time_from) OR (date == tomorrow AND time <= time_to) OR (time IS NULL)
        event_stmt = event_stmt.where(
            or_(
                and_(Event.date == today, or_(Event.time == None, Event.time >= time_from)),  # noqa: E711
                and_(Event.date == tomorrow, or_(Event.time == None, Event.time <= time_to)),  # noqa: E711
            )
        )
    elif time_from is not None:
        event_stmt = event_stmt.where(or_(Event.time == None, Event.time >= time_from))  # noqa: E711

    if categories:
        event_stmt = event_stmt.where(Event.category.in_(categories))
    # Proximity prefilter by bbox (30km) if center is known
    # BUT include events without coordinates (lat/lon = NULL)
    if center is not None:
        latc, lonc = center
        lat_min, lat_max, lon_min, lon_max = _bbox(latc, lonc, 30.0)
        event_stmt = event_stmt.where(
            or_(
                and_(Event.lat >= lat_min, Event.lat <= lat_max, Event.lon >= lon_min, Event.lon <= lon_max),
                Event.lat == None,  # noqa: E711
            )
        )
    event_stmt = event_stmt.limit(200)
    events_res = (await session.execute(event_stmt)).scalars().all()

    # Editorial pins for events (city + date window)
    pins_evt_stmt = (
        select(EditorialPin)
        .where(
            and_(
                EditorialPin.item_type == "event",
                EditorialPin.city == city,
                EditorialPin.active_from <= now.date(),
                EditorialPin.active_to >= now.date(),
            )
        )
        .order_by(EditorialPin.priority.desc())
        .limit(5)
    )
    pins_evt = (await session.execute(pins_evt_stmt)).scalars().all()
    pinned_event_ids = [p.item_id for p in pins_evt]

    # Score and sort events
    events_scored: list[tuple[float, Event]] = []
    for e in events_res:
        try:
            sc = score_event(user_ctx, e, now)
        except Exception:
            sc = 0.0
        events_scored.append((sc, e))
    events_scored.sort(key=lambda x: x[0], reverse=True)
    # Build top with pins first (preserve order), then best scored excluding duplicates
    top_events: list[Event] = []
    if pinned_event_ids:
        pinned_rows = (await session.execute(select(Event).where(Event.id.in_(pinned_event_ids)))).scalars().all()
        # Keep order according to pins
        id_to_ev = {e.id: e for e in pinned_rows}
        for pid in pinned_event_ids:
            ev = id_to_ev.get(pid)
            if ev:
                top_events.append(ev)
    for _, e in events_scored:
        if e.id not in pinned_event_ids and len(top_events) < 5:
            top_events.append(e)

    # Attach deeplinks/buttons and cast to DTO
    events_out: list[EventOut] = []
    for e in top_events:
        deeplink = None
        if e.lat is not None and e.lon is not None:
            deeplink = yandex_deeplink(e.lat, e.lon, e.title)
        buttons = _buttons_for_event({
            "source_url": e.source_url,
            "price_min": e.price_min,
            "price_max": e.price_max,
        })
        dto = EventOut.model_validate({
            "id": e.id,
            "title": e.title,
            "date": e.date,
            "time": e.time.isoformat() if e.time else None,
            "price_min": e.price_min,
            "price_max": e.price_max,
            "category": e.category,
            "venue_name": e.venue_name,
            "address": e.address,
            "lat": e.lat,
            "lon": e.lon,
            "source": e.source,
            "source_url": e.source_url,
            "quality_score": e.quality_score,
            "image_url": getattr(e, "image_url", None),
            "deeplink": deeplink,
            "buttons": buttons,
        })
        events_out.append(dto)

    # Query Places candidates
    places_out: list[PlaceOut] = []
    if center is not None:
        latc, lonc = center
        lat_min, lat_max, lon_min, lon_max = _bbox(latc, lonc, 2.0)
        place_stmt = select(Place).where(
            and_(Place.lat >= lat_min, Place.lat <= lat_max, Place.lon >= lon_min, Place.lon <= lon_max)
        )
        if categories:
            place_stmt = place_stmt.where(Place.category.in_(categories))
        place_stmt = place_stmt.limit(200)
        places_res = (await session.execute(place_stmt)).scalars().all()

        # Editorial pins for places
        pins_pl_stmt = (
            select(EditorialPin)
            .where(
                and_(
                    EditorialPin.item_type == "place",
                    EditorialPin.city == city,
                    EditorialPin.active_from <= now.date(),
                    EditorialPin.active_to >= now.date(),
                )
            )
            .order_by(EditorialPin.priority.desc())
            .limit(5)
        )
        pins_pl = (await session.execute(pins_pl_stmt)).scalars().all()
        pinned_place_ids = [p.item_id for p in pins_pl]

        # Score and sort
        places_scored: list[tuple[float, Place]] = []
        for p in places_res:
            try:
                sc = score_place(user_ctx, p, now)
            except Exception:
                sc = 0.0
            places_scored.append((sc, p))
        places_scored.sort(key=lambda x: x[0], reverse=True)
        # Compose top places: pins first, then scored
        top_places: list[Place] = []
        if pinned_place_ids:
            pinned_rows = (await session.execute(select(Place).where(Place.id.in_(pinned_place_ids)))).scalars().all()
            id_to_pl = {p.id: p for p in pinned_rows}
            for pid in pinned_place_ids:
                pl = id_to_pl.get(pid)
                if pl:
                    top_places.append(pl)
        for _, p in places_scored:
            if p.id not in pinned_place_ids and len(top_places) < 5:
                top_places.append(p)

        for p in top_places:
            deeplink = yandex_deeplink(p.lat, p.lon, p.name)
            buttons = _buttons_for_place({"phone": getattr(p, "phone", None)})
            places_out.append(
                PlaceOut.model_validate(
                    {
                        "id": p.id,
                        "name": p.name,
                        "category": p.category,
                        "address": p.address,
                        "lat": p.lat,
                        "lon": p.lon,
                        "phone": getattr(p, "phone", None),
                        "hours": getattr(p, "hours", None),
                        "rating": getattr(p, "rating", None),
                        "price_level": getattr(p, "price_level", None),
                        "source": p.source,
                        "external_id": p.external_id,
                        "image_url": getattr(p, "image_url", None),
                        "deeplink": deeplink,
                        "buttons": buttons,
                    }
                )
            )

    # NOTE: Paid events are already included in events_out with event_type='paid'
    # No separate ads needed - all monetization is through Event model now

    resp = SearchResponse(events=events_out, places=places_out, count=len(events_out) + len(places_out))

    # Cache set
    await redis.set(cache_key, resp.model_dump_json(), ex=CACHE_TTL)
    return resp


@app.post("/api/poll/create")
async def poll_create(payload: PollCreateIn, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Create a small poll of 3 candidates (2 events + 1 place)."""

    # Reuse search endpoint logic
    res = await search(
        city=payload.city,
        when=payload.when,
        date_q=None,
        lat=payload.lat,
        lon=payload.lon,
        budget_max=payload.budget_max,
        categories=None,
        session=session,
    )

    items: list[dict[str, str]] = []
    for e in res.events[:2]:
        subtitle = f"{e.date.isoformat()} • {e.venue_name}"
        items.append({"title": e.title, "subtitle": subtitle, "button_url": e.deeplink or e.source_url})
    if res.places:
        p = res.places[0]
        subtitle = p.address
        items.append({"title": p.name, "subtitle": subtitle, "button_url": p.deeplink or (p.buttons[0]["url"] if p.buttons else "")})

    return {"items": items[:3]}


@app.post("/api/ugc/submit")
async def ugc_submit(data: UGCIn) -> dict[str, Any]:
    """Queue UGC submission for moderation and extraction.

    Stores the payload into Redis list `ugc:queue` for later processing
    by a worker. In production this would enqueue an RQ job.
    """

    redis = await get_redis()
    payload: dict[str, Any] = {
        "raw_text": data.raw_text,
        "source_url": data.source_url,
        "ts": datetime.utcnow().isoformat(),
        "wants_paid_promotion": data.wants_paid_promotion or False,
    }
    if data.images:
        # keep only strings
        payload["images"] = [str(u) for u in data.images if isinstance(u, str)]
    if data.form:
        payload["form"] = dict(data.form)
    if data.user_id is not None:
        payload["user_id"] = int(data.user_id)

    # Route to appropriate queue based on paid promotion request
    queue_name = "ugc:queue:paid" if data.wants_paid_promotion else "ugc:queue"
    await redis.lpush(queue_name, json.dumps(payload, ensure_ascii=False))
    logger.info("ugc.enqueued", queue=queue_name, wants_paid=data.wants_paid_promotion)
    return {"queued": True}


@app.post("/api/ads/track")
async def track_ad_interaction(
    event_id: str,
    interaction_type: str = Query(..., pattern="^(view|click)$"),
    user_id: Optional[int] = None,
    session: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    """Track ad view or click for CPC/CPM analytics.

    Args:
        event_id: UUID of the event
        interaction_type: 'view' or 'click'
        user_id: Optional Telegram user ID
        session: DB session

    Returns:
        {"tracked": True}
    """
    try:
        import uuid as _uuid
        eid = _uuid.UUID(event_id)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid event_id")

    # Check if event exists and is paid
    event = await session.get(Event, eid)
    if not event:
        raise HTTPException(status_code=404, detail="event not found")

    if event.event_type != "paid":
        # Don't track free events
        return {"tracked": False}

    # Create interaction record
    interaction = AdInteraction(
        event_id=eid,
        user_id=user_id,
        interaction_type=interaction_type,
    )
    session.add(interaction)

    # Update event counters
    if interaction_type == "view":
        event.views += 1
    elif interaction_type == "click":
        event.clicks += 1

        # Update spent budget for CPC/CPM
        if event.pricing_model == "cpc" and event.budget:
            # Assume price_per_unit or calculate from budget
            # For simplicity, we'll need price_per_unit in the event or placement_request
            # For now, just increment spent_budget by a default amount
            # TODO: Get actual CPC price from placement_request
            event.spent_budget = (event.spent_budget or 0) + 3000  # 30 rubles in kopecks (placeholder)

            # Auto-stop if budget exhausted
            if event.spent_budget >= event.budget:
                event.status = "past"  # or create a new status 'budget_exhausted'
                logger.info("ad.budget_exhausted", event_id=str(eid))

        elif event.pricing_model == "cpm" and event.budget:
            # CPM: charge per 1000 views, not clicks
            pass  # Handle in view tracking

    # Update spent budget for CPM on views
    if interaction_type == "view" and event.pricing_model == "cpm" and event.budget:
        # Charge per view
        # TODO: Get actual CPM price from placement_request
        cpm_price = 30000  # 300 rubles per 1000 views = 0.3 rubles per view = 30 kopecks (placeholder)
        event.spent_budget = (event.spent_budget or 0) + (cpm_price // 1000)

        if event.spent_budget >= event.budget:
            event.status = "past"
            logger.info("ad.budget_exhausted", event_id=str(eid))

    await session.commit()
    logger.info("ad.interaction_tracked", event_id=str(eid), type=interaction_type, user_id=user_id)

    return {"tracked": True}


# --------- Monetization Endpoints ---------


@app.post("/api/monetization/calculate-price", response_model=PlacementPriceResponse)
async def calculate_placement_price(
    request: PlacementPriceRequest,
    session: AsyncSession = Depends(get_session),
) -> PlacementPriceResponse:
    """Calculate placement price using dynamic formula.

    Formula: Price = ((x * r) * y) * Q

    Args:
        request: Placement details (type, datetime, targeting)
        session: DB session

    Returns:
        PlacementPriceResponse with calculated price and breakdown
    """
    monetization = MonetizationService(session)

    try:
        result = await monetization.calculate_placement_price(
            placement_type=request.placement_type,
            event_datetime=request.event_datetime,
            target_city=request.target_city,
            target_zone=request.target_zone,
        )
        logger.info(
            "monetization.price_calculated",
            placement_type=request.placement_type,
            price=result["price"],
            audience_size=result["audience_size"],
        )
        return PlacementPriceResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("monetization.calculation_error", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to calculate price")


@app.get("/api/monetization/settings")
async def get_monetization_settings(
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get all monetization settings.

    Returns:
        Dictionary of setting_key -> setting_value
    """
    monetization = MonetizationService(session)
    try:
        settings_dict = await monetization.get_all_settings()
        # Convert Decimal to float for JSON serialization
        return {k: float(v) for k, v in settings_dict.items()}
    except Exception as e:
        logger.error("monetization.get_settings_error", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to get settings")


@app.put("/api/monetization/settings")
async def update_monetization_setting(
    update: MonetizationSettingUpdate,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Update a monetization setting.

    Args:
        update: Setting key, value, and optional updated_by
        session: DB session

    Returns:
        Success confirmation
    """
    monetization = MonetizationService(session)
    try:
        await monetization.update_setting(
            key=update.setting_key,
            value=update.setting_value,
            updated_by=update.updated_by,
        )
        logger.info(
            "monetization.setting_updated",
            key=update.setting_key,
            value=update.setting_value,
            updated_by=update.updated_by,
        )
        return {"success": True, "setting_key": update.setting_key, "new_value": update.setting_value}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("monetization.update_setting_error", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to update setting")


@app.get("/api/monetization/audience-size")
async def get_audience_size(
    placement_type: str = Query(..., pattern="^(broadcast_all|broadcast_city|broadcast_zone|hot)$"),
    target_city: Optional[str] = Query(None),
    target_zone: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
) -> dict[str, int]:
    """Get estimated audience size for targeting parameters.

    Args:
        placement_type: Type of broadcast
        target_city: Optional city for targeting
        target_zone: Optional zone for targeting
        session: DB session

    Returns:
        {"audience_size": int}
    """
    monetization = MonetizationService(session)
    try:
        size = await monetization.get_audience_size(
            placement_type=placement_type,
            target_city=target_city,
            target_zone=target_zone,
        )
        logger.info(
            "monetization.audience_size_calculated",
            placement_type=placement_type,
            city=target_city,
            zone=target_zone,
            size=size,
        )
        return {"audience_size": size}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("monetization.audience_size_error", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to calculate audience size")


def run() -> None:
    """Entrypoint for `python -m app.api.main`."""

    import uvicorn

    uvicorn.run(
        "app.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.env == "dev",
        factory=False,
    )


if __name__ == "__main__":
    run()
from app.db.models import EventImage
@app.get("/api/events/{event_id}/images")
async def event_images(event_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, list[str]]:
    try:
        import uuid as _uuid

        eid = _uuid.UUID(event_id)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid id")
    rows = (
        await session.execute(
            select(EventImage).where(EventImage.event_id == eid).order_by(EventImage.priority.asc())
        )
    ).scalars().all()
    urls = [r.url for r in rows]
    if not urls:
        ev = await session.get(Event, eid)
        if ev and getattr(ev, "image_url", None):
            urls = [str(ev.image_url)]
    return {"images": urls}
