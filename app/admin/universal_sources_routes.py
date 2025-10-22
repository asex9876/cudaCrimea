"""Admin routes for managing universal parsing sources.

Allows admins to add, edit, delete, and monitor universal sources.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import structlog
from fastapi import Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.auth import require_admin_auth
from app.db.session import get_async_session
from app.db.models import UniversalSource
from app.admin.templates import templates

logger = structlog.get_logger(module="admin.universal_sources")


# Lazy import to avoid circular dependencies
def _get_universal_parser():
    from app.ingestors.universal_parser import process_source
    return process_source


async def universal_sources_page(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
    _admin_user: str = Depends(require_admin_auth),
) -> HTMLResponse:
    """Display universal sources management page."""

    # Get all sources
    result = await session.execute(
        select(UniversalSource).order_by(UniversalSource.created_at.desc())
    )
    sources = result.scalars().all()

    # Calculate statistics
    total_sources = len(sources)
    active_sources = sum(1 for s in sources if s.is_active)
    total_events_parsed = sum(s.total_parsed for s in sources)
    sources_with_errors = sum(1 for s in sources if s.last_error is not None)

    stats = {
        "total_sources": total_sources,
        "active_sources": active_sources,
        "total_events_parsed": total_events_parsed,
        "sources_with_errors": sources_with_errors,
    }

    return templates.TemplateResponse(
        "universal_sources.html",
        {
            "request": request,
            "sources": sources,
            "stats": stats,
        },
    )


async def create_source(
    request: Request,
    url: str = Form(...),
    name: str = Form(...),
    description: str = Form(None),
    city: str = Form(None),
    parse_interval_minutes: int = Form(30),
    session: AsyncSession = Depends(get_async_session),
    _admin_user: str = Depends(require_admin_auth),
) -> RedirectResponse:
    """Create a new universal source."""

    try:
        # Check if URL already exists
        existing = await session.execute(
            select(UniversalSource).where(UniversalSource.url == url)
        )
        if existing.scalar_one_or_none():
            logger.warning("universal_sources.duplicate_url", url=url)
            # Redirect with error (you could add flash messages here)
            return RedirectResponse(
                url="/admin/universal-sources?error=URL+already+exists",
                status_code=status.HTTP_303_SEE_OTHER,
            )

        # Create new source
        source = UniversalSource(
            id=uuid.uuid4(),
            url=url,
            name=name,
            description=description,
            city=city,
            parse_interval_minutes=parse_interval_minutes,
            is_active=True,
            total_parsed=0,
            created_by=_admin_user,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        session.add(source)
        await session.commit()

        logger.info("universal_sources.created", source_id=str(source.id), url=url)

        return RedirectResponse(
            url="/admin/universal-sources",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    except Exception as e:
        logger.error("universal_sources.create_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


async def toggle_source(
    source_id: str,
    session: AsyncSession = Depends(get_async_session),
    _admin_user: str = Depends(require_admin_auth),
) -> JSONResponse:
    """Toggle source active/inactive status."""

    try:
        source_uuid = uuid.UUID(source_id)

        # Get current source
        result = await session.execute(
            select(UniversalSource).where(UniversalSource.id == source_uuid)
        )
        source = result.scalar_one_or_none()

        if not source:
            raise HTTPException(status_code=404, detail="Source not found")

        # Toggle active status
        new_status = not source.is_active
        await session.execute(
            update(UniversalSource)
            .where(UniversalSource.id == source_uuid)
            .values(is_active=new_status, updated_at=datetime.now())
        )
        await session.commit()

        logger.info(
            "universal_sources.toggled",
            source_id=source_id,
            is_active=new_status,
        )

        return JSONResponse({"success": True, "is_active": new_status})

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID")
    except Exception as e:
        logger.error("universal_sources.toggle_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


async def delete_source_route(
    source_id: str,
    session: AsyncSession = Depends(get_async_session),
    _admin_user: str = Depends(require_admin_auth),
) -> JSONResponse:
    """Delete a universal source."""

    try:
        source_uuid = uuid.UUID(source_id)

        # Delete source
        result = await session.execute(
            delete(UniversalSource).where(UniversalSource.id == source_uuid)
        )

        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Source not found")

        await session.commit()

        logger.info("universal_sources.deleted", source_id=source_id)

        return JSONResponse({"success": True})

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID")
    except Exception as e:
        logger.error("universal_sources.delete_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


async def parse_now(
    source_id: str,
    session: AsyncSession = Depends(get_async_session),
    _admin_user: str = Depends(require_admin_auth),
) -> JSONResponse:
    """Manually trigger parsing for a source."""

    try:
        source_uuid = uuid.UUID(source_id)

        # Get source
        result = await session.execute(
            select(UniversalSource).where(UniversalSource.id == source_uuid)
        )
        source = result.scalar_one_or_none()

        if not source:
            raise HTTPException(status_code=404, detail="Source not found")

        # Parse source
        process_source_func = _get_universal_parser()
        events_added = await process_source_func(session, source)

        logger.info(
            "universal_sources.manual_parse",
            source_id=source_id,
            events_added=events_added,
        )

        return JSONResponse({
            "success": True,
            "events_added": events_added,
        })

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID")
    except Exception as e:
        logger.error("universal_sources.parse_failed", error=str(e), source_id=source_id)
        return JSONResponse({
            "success": False,
            "error": str(e),
        }, status_code=500)


async def update_source(
    source_id: str,
    request: Request,
    name: str = Form(...),
    description: str = Form(None),
    city: str = Form(None),
    parse_interval_minutes: int = Form(30),
    session: AsyncSession = Depends(get_async_session),
    _admin_user: str = Depends(require_admin_auth),
) -> RedirectResponse:
    """Update source settings."""

    try:
        source_uuid = uuid.UUID(source_id)

        # Update source
        await session.execute(
            update(UniversalSource)
            .where(UniversalSource.id == source_uuid)
            .values(
                name=name,
                description=description,
                city=city,
                parse_interval_minutes=parse_interval_minutes,
                updated_at=datetime.now(),
            )
        )
        await session.commit()

        logger.info("universal_sources.updated", source_id=source_id)

        return RedirectResponse(
            url="/admin/universal-sources",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID")
    except Exception as e:
        logger.error("universal_sources.update_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
