"""Simplified parsers routes - only Universal and Telegram AI parsers."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.auth import get_current_admin_user, require_login
from app.core import templates, runtime_config as rc
from app.db.models import UniversalSource, TelegramChannel, User
from app.db.session import get_session

logger = structlog.get_logger(module="admin.parsers")
router = APIRouter(prefix="/admin/parsers", tags=["admin-parsers"])


@router.get("", response_class=HTMLResponse)
@require_login
async def parsers_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_admin_user),
) -> HTMLResponse:
    """Страница парсеров - Universal Web Parser + Telegram AI Parser."""

    # === Universal Sources ===
    universal_sources = (await session.execute(
        select(UniversalSource).order_by(UniversalSource.created_at.desc())
    )).scalars().all()

    universal_stats = {
        "total_sources": len(universal_sources),
        "active_sources": sum(1 for s in universal_sources if s.is_active),
        "total_events_parsed": sum(s.total_parsed for s in universal_sources),
        "sources_with_errors": sum(1 for s in universal_sources if s.last_error is not None),
    }

    # === Telegram Channels ===
    channels = (await session.execute(
        select(TelegramChannel).order_by(TelegramChannel.added_at.desc())
    )).scalars().all()

    telegram_stats = {
        "total_channels": len(channels),
        "active_channels": sum(1 for c in channels if c.is_active),
    }

    # Runtime config for intervals
    universal_interval = rc.get("ingest_universal_parser_minutes", 30)
    telegram_interval = rc.get("ingest_telegram_minutes", 45)

    return templates.TemplateResponse(
        request=request,
        name="parsers_simplified.html",
        context={
            "universal_sources": universal_sources,
            "universal_stats": universal_stats,
            "universal_interval": universal_interval,
            "channels": channels,
            "telegram_stats": telegram_stats,
            "telegram_interval": telegram_interval,
        },
    )
