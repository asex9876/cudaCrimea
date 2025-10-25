"""Admin routes for viewing archived events."""

from __future__ import annotations

from datetime import datetime, date, timedelta
from typing import Optional
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from app.db.models import Event
from app.db.session import get_session

logger = structlog.get_logger(module="admin.archive")
router = APIRouter(prefix="/archive", tags=["admin-archive"])


def get_templates() -> Jinja2Templates:
    """Get Jinja2 templates instance."""
    return Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def require_login(request: Request) -> None:
    """Check if user is authenticated."""
    if not request.session.get("auth") and not request.headers.get("X-Remote-User"):
        raise HTTPException(status_code=302, detail="redirect", headers={"Location": "/login"})


@router.get("", response_class=HTMLResponse)
async def archive_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    """Страница архивных событий."""
    require_login(request)
    templates = get_templates()

    # Статистика архива
    total_archived_stmt = sa.select(func.count(Event.id)).where(Event.status == "past")
    total_archived = await session.scalar(total_archived_stmt) or 0

    # Самое старое событие в архиве
    oldest_stmt = sa.select(Event.date).where(Event.status == "past").order_by(Event.date.asc()).limit(1)
    oldest_date = await session.scalar(oldest_stmt)

    # Сколько будет удалено через 30 дней
    cutoff_date = datetime.now().date() - timedelta(days=30)
    will_delete_stmt = sa.select(func.count(Event.id)).where(
        Event.status == "past",
        Event.date < cutoff_date
    )
    will_delete = await session.scalar(will_delete_stmt) or 0

    # События по городам
    city_stats_stmt = (
        sa.select(
            Event.city,
            func.count(Event.id).label("count")
        )
        .where(Event.status == "past")
        .group_by(Event.city)
        .order_by(sa.text("count DESC"))
    )
    city_stats_result = await session.execute(city_stats_stmt)
    city_stats = [{"city": row[0], "count": row[1]} for row in city_stats_result]

    # События по категориям
    category_stats_stmt = (
        sa.select(
            Event.category,
            func.count(Event.id).label("count")
        )
        .where(Event.status == "past")
        .group_by(Event.category)
        .order_by(sa.text("count DESC"))
    )
    category_stats_result = await session.execute(category_stats_stmt)
    category_stats = [{"category": row[0], "count": row[1]} for row in category_stats_result]

    stats = {
        "total_archived": total_archived,
        "oldest_date": oldest_date,
        "will_delete": will_delete,
        "city_stats": city_stats,
        "category_stats": category_stats,
    }

    return templates.TemplateResponse(
        request=request,
        name="archive.html",
        context={"stats": stats},
    )


@router.get("/api/events", response_class=JSONResponse)
async def get_archived_events(
    request: Request,
    city: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(50, le=500),
    offset: int = Query(0),
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    """API для получения архивных событий с фильтрацией."""
    require_login(request)

    # Базовый запрос
    conditions = [Event.status == "past"]

    # Фильтры
    if city:
        conditions.append(Event.city == city)

    if category:
        conditions.append(Event.category == category)

    if date_from:
        try:
            date_from_obj = datetime.fromisoformat(date_from).date()
            conditions.append(Event.date >= date_from_obj)
        except ValueError:
            pass

    if date_to:
        try:
            date_to_obj = datetime.fromisoformat(date_to).date()
            conditions.append(Event.date <= date_to_obj)
        except ValueError:
            pass

    if search:
        search_pattern = f"%{search}%"
        conditions.append(
            or_(
                Event.title.ilike(search_pattern),
                Event.description.ilike(search_pattern),
                Event.venue_name.ilike(search_pattern),
            )
        )

    # Запрос событий
    stmt = (
        sa.select(Event)
        .where(and_(*conditions))
        .order_by(Event.date.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    events = result.scalars().all()

    # Общее количество для пагинации
    count_stmt = sa.select(func.count(Event.id)).where(and_(*conditions))
    total = await session.scalar(count_stmt) or 0

    # Форматируем события
    events_data = []
    for event in events:
        events_data.append({
            "id": str(event.id),
            "title": event.title,
            "date": str(event.date),
            "end_date": str(event.end_date) if event.end_date else None,
            "time": str(event.time) if event.time else None,
            "city": event.city,
            "venue_name": event.venue_name,
            "address": event.address,
            "category": event.category,
            "price_min": event.price_min,
            "price_max": event.price_max,
            "description": event.description,
            "source": event.source,
            "image_url": event.image_url,
        })

    return JSONResponse({
        "events": events_data,
        "total": total,
        "limit": limit,
        "offset": offset,
    })


@router.delete("/api/events/{event_id}")
async def delete_archived_event(
    request: Request,
    event_id: str,
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    """Удалить конкретное архивное событие."""
    require_login(request)

    # Проверяем что событие в архиве
    stmt = sa.select(Event).where(Event.id == event_id, Event.status == "past")
    result = await session.execute(stmt)
    event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(status_code=404, detail="Архивное событие не найдено")

    await session.delete(event)
    await session.commit()

    logger.info("archive.event_deleted", event_id=event_id, title=event.title)

    return JSONResponse({"success": True})


@router.post("/api/cleanup")
async def manual_cleanup(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    """Ручная очистка архива (старше 30 дней)."""
    require_login(request)

    cutoff_date = datetime.now().date() - timedelta(days=30)

    stmt = sa.delete(Event).where(
        Event.status == "past",
        Event.date < cutoff_date
    )
    result = await session.execute(stmt)
    await session.commit()

    deleted_count = result.rowcount or 0

    logger.info("archive.manual_cleanup", deleted_count=deleted_count, cutoff_date=str(cutoff_date))

    return JSONResponse({
        "success": True,
        "deleted_count": deleted_count,
        "cutoff_date": str(cutoff_date),
    })
