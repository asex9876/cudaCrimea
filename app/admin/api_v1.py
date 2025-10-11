from __future__ import annotations

import hashlib
import json
from datetime import date as _date, datetime, time as _time, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Iterable

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from redis import asyncio as aioredis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.utils.render import render_event_card
from app.core.config import get_settings
from app.core.llm.extractor import EventDraft, extract_event_fields
from app.db.dao.events import upsert_event
from app.db.models import AdInteraction, Event, EventImage
from app.db.session import get_session

settings = get_settings()

router = APIRouter(prefix="/api/v1", tags=["admin-api"])


async def get_redis() -> aioredis.Redis:
    return aioredis.from_url(str(settings.redis_url), decode_responses=True)


def ensure_api_auth(request: Request) -> None:
    if not request.session.get("auth"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not_authenticated")


def _make_queue_id(raw: str) -> str:
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _load_payload(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {"raw_text": raw}
    if not isinstance(data, dict):
        data = {"raw_text": raw}
    return data


def _extract_form(payload: dict[str, Any]) -> dict[str, Any] | None:
    form = payload.get("form")
    if isinstance(form, dict):
        return form
    raw_text = payload.get("raw_text")
    if isinstance(raw_text, str) and raw_text.startswith("FORM:"):
        raw_form = raw_text.split("FORM:", 1)[1].strip()
        try:
            parsed = json.loads(raw_form)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            try:
                norm = raw_form.replace("'", '"').replace(": None", ": null").replace(" None,", " null,")
                parsed = json.loads(norm)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                return None
    return None


def _collect_images(payload: dict[str, Any]) -> list[str]:
    images: list[str] = []
    raw_images = payload.get("images")
    if isinstance(raw_images, Iterable) and not isinstance(raw_images, (str, bytes, dict)):
        for item in raw_images:
            if isinstance(item, str) and item:
                images.append(item)
    image_url = payload.get("image_url")
    if isinstance(image_url, str) and image_url:
        images.insert(0, image_url)
    seen: set[str] = set()
    unique: list[str] = []
    for img in images:
        if img not in seen:
            seen.add(img)
            unique.append(img)
    return unique


def _build_preview(payload: dict[str, Any]) -> tuple[dict[str, Any], str, list[list[dict[str, str]]]]:
    form = _extract_form(payload)
    preview: dict[str, Any] = {
        "title": None,
        "date_iso": None,
        "time_24h": None,
        "venue_name": None,
        "city": None,
        "address": None,
        "price_min": None,
        "price_max": None,
        "category": None,
        "source_url": payload.get("source_url"),
    }
    if isinstance(form, dict):
        preview.update({
            "title": form.get("title"),
            "date_iso": form.get("date_iso"),
            "time_24h": form.get("time_24h"),
            "venue_name": form.get("venue_name"),
            "city": form.get("city"),
            "address": form.get("address"),
            "price_min": form.get("price_min"),
            "price_max": form.get("price_max"),
            "category": form.get("category"),
            "source_url": form.get("source_url") or preview.get("source_url"),
        })
    caption_obj = SimpleNamespace(
        title=preview.get("title"),
        category=preview.get("category"),
        venue_name=preview.get("venue_name") or "",
        address=preview.get("address") or "",
        date=preview.get("date_iso") or "",
        time=preview.get("time_24h"),
        price_min=preview.get("price_min"),
        price_max=preview.get("price_max"),
    )
    caption = render_event_card(caption_obj)
    src = str(preview.get("source_url") or "").strip()
    if src:
        caption = caption + f"\nСайт: {src}"
    buttons: list[list[dict[str, str]]] = []
    if src:
        row: list[dict[str, str]] = [{"text": "Сайт", "url": src}]
        if preview.get("price_min") is not None or preview.get("price_max") is not None:
            row.append({"text": "Билеты", "url": src})
        buttons.append(row)
    return preview, caption, buttons


def _parse_queue_item(raw: str) -> "UGCItem":
    payload = _load_payload(raw)
    images = _collect_images(payload)
    preview, caption, buttons = _build_preview(payload)
    submitted_at = None
    ts = payload.get("ts")
    if isinstance(ts, str):
        try:
            submitted_at = datetime.fromisoformat(ts)
        except ValueError:
            submitted_at = None
    return UGCItem(
        id=_make_queue_id(raw),
        raw=raw,
        payload=payload,
        submitted_at=submitted_at,
        images=images,
        preview=UGCPreview(**preview),
        caption=caption,
        buttons=[[UGCButton(**btn) for btn in row] for row in buttons],
    )


def _split_queue_items(items: list[str], offset: int, limit: int) -> list[str]:
    if not items:
        return []
    start = offset
    stop = offset + limit
    return items[start:stop]


async def _get_raw_by_id(redis: aioredis.Redis, item_id: str) -> str | None:
    items = await redis.lrange("ugc:queue", 0, -1)
    for raw in items:
        if _make_queue_id(raw) == item_id:
            return raw
    return None


async def _set_raw_by_id(redis: aioredis.Redis, item_id: str, new_raw: str) -> None:
    items = await redis.lrange("ugc:queue", 0, -1)
    for idx, raw in enumerate(items):
        if _make_queue_id(raw) == item_id:
            await redis.lset("ugc:queue", idx, new_raw)
            return
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ugc_item_not_found")


async def _approve_payload(payload: dict[str, Any], session: AsyncSession) -> Event:
    raw_text = payload.get("raw_text", "")
    source_url = payload.get("source_url")
    form = _extract_form(payload)
    if form and isinstance(form, dict):
        draft = EventDraft(
            title=form.get("title"),
            date_iso=form.get("date_iso"),
            time_24h=form.get("time_24h"),
            venue_name=form.get("venue_name"),
            address=form.get("address"),
            price_min=form.get("price_min"),
            price_max=form.get("price_max"),
            category=form.get("category"),
            source_url=form.get("source_url") or source_url,
        )
        lat = form.get("lat") if isinstance(form.get("lat"), (int, float)) else None
        lon = form.get("lon") if isinstance(form.get("lon"), (int, float)) else None
    else:
        draft = extract_event_fields(raw_text, source_url)
        lat = None
        lon = None
    if not draft.title or not draft.date_iso:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_draft")
    try:
        event_date = _date.fromisoformat(draft.date_iso)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_date") from exc
    try:
        event_time = _time.fromisoformat(draft.time_24h) if draft.time_24h else None
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_time") from exc
    event = await upsert_event(
        session,
        title=draft.title,
        date_=event_date,
        time_=event_time,
        venue_name=draft.venue_name or "",
        address=draft.address or "",
        lat=lat,
        lon=lon,
        price_min=draft.price_min,
        price_max=draft.price_max,
        category=draft.category or "other",
        source="ugc",
        source_url=draft.source_url or (source_url or ""),
        quality_base=0.5,
    )
    images = _collect_images(payload)
    if images:
        await session.execute(sa.delete(EventImage).where(EventImage.event_id == event.id))
        for idx, url in enumerate(images):
            if url:
                session.add(EventImage(event_id=event.id, url=url, priority=idx))
        event.image_url = images[0]
    await session.commit()
    await session.refresh(event)
    return event


class UGCButton(BaseModel):
    text: str
    url: str


class UGCPreview(BaseModel):
    title: str | None = None
    date_iso: str | None = None
    time_24h: str | None = None
    venue_name: str | None = None
    city: str | None = None
    address: str | None = None
    price_min: int | None = Field(default=None)
    price_max: int | None = Field(default=None)
    category: str | None = None
    source_url: str | None = None


class UGCItem(BaseModel):
    id: str
    raw: str
    payload: dict[str, Any]
    submitted_at: datetime | None = None
    images: list[str]
    preview: UGCPreview
    caption: str
    buttons: list[list[UGCButton]]


class UGCListResponse(BaseModel):
    total: int
    items: list[UGCItem]


class UGCApproveBody(BaseModel):
    payload: dict[str, Any] | None = None


class UGCRejectBody(BaseModel):
    reason: str | None = None


class UGCUpdateBody(BaseModel):
    payload: dict[str, Any]


class DashboardTask(BaseModel):
    id: str
    title: str | None = None
    status: str = "pending"
    submitted_at: datetime | None = None


class DashboardSummary(BaseModel):
    new_requests: int
    published_today: int
    ctr_week: float
    error_count: int
    tasks: list[DashboardTask]


@router.get("/dashboard/summary", response_model=DashboardSummary)
async def dashboard_summary(
    request: Request,
    session: AsyncSession = Depends(get_session),
    redis: aioredis.Redis = Depends(get_redis),
) -> DashboardSummary:
    ensure_api_auth(request)
    queue_size = await redis.llen("ugc:queue")
    today = _date.today()
    published_today = await session.scalar(
        select(func.count()).select_from(Event).where(func.date(Event.created_at) == today)
    ) or 0
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    # Use AdInteraction for clicks tracking
    total_clicks = await session.scalar(
        select(func.count()).select_from(AdInteraction).where(AdInteraction.created_at >= week_ago, AdInteraction.interaction_type == "click")
    ) or 0
    total_views = await session.scalar(
        select(func.count()).select_from(AdInteraction).where(AdInteraction.created_at >= week_ago, AdInteraction.interaction_type == "view")
    ) or 0
    ctr = (total_clicks / total_views) if total_views else 0.0
    error_count = await redis.llen("ingest:errors")
    raw_items = await redis.lrange("ugc:queue", 0, 4)
    task_items: list[DashboardTask] = []
    for raw in raw_items:
        item = _parse_queue_item(raw)
        task_items.append(
            DashboardTask(
                id=item.id,
                title=item.preview.title,
                status="pending",
                submitted_at=item.submitted_at,
            )
        )
    return DashboardSummary(
        new_requests=queue_size,
        published_today=published_today,
        ctr_week=round(ctr, 4),
        error_count=error_count,
        tasks=task_items,
    )


@router.get("/ugc", response_model=UGCListResponse)
async def ugc_list(
    request: Request,
    status_filter: str = Query("pending"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    redis: aioredis.Redis = Depends(get_redis),
) -> UGCListResponse:
    ensure_api_auth(request)
    if status_filter != "pending":
        return UGCListResponse(total=0, items=[])
    total = await redis.llen("ugc:queue")
    if total == 0:
        return UGCListResponse(total=0, items=[])
    items = await redis.lrange("ugc:queue", 0, -1)
    slice_items = _split_queue_items(items, offset, limit)
    parsed = [_parse_queue_item(raw) for raw in slice_items]
    return UGCListResponse(total=total, items=parsed)


@router.get("/ugc/{item_id}", response_model=UGCItem)
async def ugc_detail(
    item_id: str,
    request: Request,
    redis: aioredis.Redis = Depends(get_redis),
) -> UGCItem:
    ensure_api_auth(request)
    raw = await _get_raw_by_id(redis, item_id)
    if raw is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ugc_item_not_found")
    return _parse_queue_item(raw)


@router.patch("/ugc/{item_id}", response_model=UGCItem)
async def ugc_update(
    item_id: str,
    body: UGCUpdateBody,
    request: Request,
    redis: aioredis.Redis = Depends(get_redis),
) -> UGCItem:
    ensure_api_auth(request)
    new_raw = json.dumps(body.payload, ensure_ascii=False)
    await _set_raw_by_id(redis, item_id, new_raw)
    return _parse_queue_item(new_raw)


@router.post("/ugc/{item_id}/approve")
async def ugc_approve(
    item_id: str,
    body: UGCApproveBody,
    request: Request,
    session: AsyncSession = Depends(get_session),
    redis: aioredis.Redis = Depends(get_redis),
) -> dict[str, Any]:
    ensure_api_auth(request)
    raw = await _get_raw_by_id(redis, item_id)
    if raw is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ugc_item_not_found")
    payload = body.payload if body.payload is not None else _load_payload(raw)
    event = await _approve_payload(payload, session)
    await redis.lrem("ugc:queue", 1, raw)
    return {"status": "approved", "event_id": str(event.id)}


@router.post("/ugc/{item_id}/reject")
async def ugc_reject(
    item_id: str,
    body: UGCRejectBody | None,
    request: Request,
    redis: aioredis.Redis = Depends(get_redis),
) -> dict[str, Any]:
    ensure_api_auth(request)
    raw = await _get_raw_by_id(redis, item_id)
    if raw is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ugc_item_not_found")
    await redis.lrem("ugc:queue", 1, raw)
    return {"status": "rejected", "reason": (body.reason if body else None)}
