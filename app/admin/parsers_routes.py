"""Simplified parsers routes - only Universal and Telegram AI parsers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import runtime_config as rc
from app.db.models import UniversalSource, TelegramChannel
from app.db.session import get_session

logger = structlog.get_logger(module="admin.parsers")
router = APIRouter(prefix="/parsers", tags=["admin-parsers"])


def get_templates() -> Jinja2Templates:
    """Get Jinja2 templates instance."""
    return Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def require_login(request: Request) -> None:
    """Check if user is authenticated."""
    if not request.session.get("auth") and not request.headers.get("X-Remote-User"):
        raise HTTPException(status_code=302, detail="redirect", headers={"Location": "/login"})


@router.get("", response_class=HTMLResponse)
async def parsers_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    """Страница парсеров - Universal Web Parser + Telegram AI Parser."""
    require_login(request)
    templates = get_templates()

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
