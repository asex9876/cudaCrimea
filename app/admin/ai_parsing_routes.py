"""AI Parsing management routes for admin panel.

Provides UI for:
- Parsing posters/flyers (Vision AI)
- Finding duplicate events (semantic search)
- Validating and auto-fixing event data
- Bulk embedding generation
"""

from __future__ import annotations

import json
from typing import Any
from datetime import datetime, timedelta

from fastapi import Request, Form, Depends, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy import func, select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import Event
from app.db.session import get_session

import structlog

logger = structlog.get_logger(module="admin.ai_parsing")


# Lazy imports to avoid ModuleNotFoundError if openai is not installed
def _get_vision_parser():
    from app.core.llm.vision_parser import get_vision_parser
    return get_vision_parser()


def _get_embedding_service():
    from app.core.services.embedding import get_embedding_service
    return get_embedding_service()


def _get_validation_service():
    from app.core.services.validation import get_validation_service
    return get_validation_service()


def _get_find_similar_events():
    from app.db.dao.events import find_similar_events
    return find_similar_events


def _get_generate_and_save_embedding():
    from app.db.dao.events import generate_and_save_embedding
    return generate_and_save_embedding


def require_login(request: Request) -> None:
    """Check if user is authenticated."""
    if not request.session.get("auth") and not request.headers.get("X-Remote-User"):
        raise HTTPException(status_code=302, detail="redirect", headers={"Location": "/login"})
    if not request.session.get("auth"):
        request.session["auth"] = True


def ensure_csrf(request: Request) -> str:
    """Ensure CSRF token exists."""
    import secrets
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(16)
        request.session["csrf"] = token
    return token


def check_csrf(request: Request, csrf: str) -> None:
    """Verify CSRF token."""
    token = request.session.get("csrf")
    if not token or token != csrf:
        raise HTTPException(status_code=403, detail="CSRF validation failed")


async def ai_parsing_page(request: Request, session: AsyncSession = Depends(get_session)) -> Any:
    """AI Parsing main page with all tools."""
    require_login(request)
    csrf = ensure_csrf(request)

    # Get stats
    total_events = await session.execute(select(func.count(Event.id)))
    total_events = total_events.scalar() or 0

    events_with_embeddings = await session.execute(
        select(func.count(Event.id)).where(Event.embedding.isnot(None))
    )
    events_with_embeddings = events_with_embeddings.scalar() or 0

    events_with_extended_fields = await session.execute(
        select(func.count(Event.id)).where(
            or_(
                Event.age_restriction.isnot(None),
                Event.organizer.isnot(None),
                Event.end_time.isnot(None),
            )
        )
    )
    events_with_extended_fields = events_with_extended_fields.scalar() or 0

    from pathlib import Path
    from fastapi.templating import Jinja2Templates

    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

    return templates.TemplateResponse(
        "ai_parsing.html",
        {
            "request": request,
            "csrf": csrf,
            "total_events": total_events,
            "events_with_embeddings": events_with_embeddings,
            "events_with_extended_fields": events_with_extended_fields,
            "embedding_coverage": round(events_with_embeddings / total_events * 100, 1) if total_events > 0 else 0,
        },
    )


async def parse_poster(
    request: Request,
    csrf: str = Form(...),
    image: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Parse event from uploaded poster image."""
    require_login(request)
    check_csrf(request, csrf)

    try:
        # Save uploaded file temporarily
        from pathlib import Path
        import shutil
        import base64

        uploads_dir = Path(__file__).parent / "uploads"
        uploads_dir.mkdir(exist_ok=True)

        file_path = uploads_dir / f"poster_{datetime.now().timestamp()}_{image.filename}"

        with file_path.open("wb") as buffer:
            shutil.copyfileobj(image.file, buffer)

        # Read file and encode to base64
        with open(file_path, "rb") as f:
            image_data = f.read()
            image_base64 = f"data:image/{image.content_type.split('/')[-1]};base64,{base64.b64encode(image_data).decode()}"

        # Parse with Vision AI
        vision_parser = _get_vision_parser()
        event_draft = vision_parser.parse_image_base64(image_base64, detail="high")

        # Clean up temp file
        file_path.unlink()

        if not event_draft:
            return JSONResponse(
                {"success": False, "error": "Не удалось извлечь данные из изображения"},
                status_code=400,
            )

        # Convert to dict
        result = event_draft.model_dump()

        logger.info("ai_parsing.poster_parsed", title=event_draft.title, category=event_draft.category)

        return JSONResponse({"success": True, "data": result})

    except Exception as e:
        logger.error("ai_parsing.poster_parse_failed", error=str(e))
        return JSONResponse(
            {"success": False, "error": f"Ошибка обработки: {str(e)}"},
            status_code=500,
        )


async def find_duplicates(
    request: Request,
    csrf: str = Form(...),
    event_id: str = Form(...),
    threshold: float = Form(0.85),
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Find duplicate events using semantic similarity."""
    require_login(request)
    check_csrf(request, csrf)

    try:
        from uuid import UUID

        # Get event
        event = await session.get(Event, UUID(event_id))
        if not event:
            return JSONResponse(
                {"success": False, "error": "Событие не найдено"},
                status_code=404,
            )

        # Generate embedding if needed
        if not event.embedding:
            embedding_service = _get_embedding_service()
            embedding = embedding_service.generate_event_embedding(
                title=event.title,
                date=str(event.date) if event.date else None,
                venue=event.venue_name,
                description=event.description,
            )
        else:
            embedding = event.embedding

        # Find similar events
        find_similar_events = _get_find_similar_events()
        similar = await find_similar_events(
            session,
            query_embedding=embedding,
            threshold=threshold,
            limit=10,
            exclude_event_id=event_id,
        )

        # Format results
        results = []
        for similar_event, similarity in similar:
            results.append({
                "id": str(similar_event.id),
                "title": similar_event.title,
                "date": str(similar_event.date),
                "venue": similar_event.venue_name,
                "source": similar_event.source,
                "similarity": round(similarity, 3),
                "similarity_percent": round(similarity * 100, 1),
            })

        logger.info("ai_parsing.duplicates_found", event_id=event_id, count=len(results))

        return JSONResponse({"success": True, "duplicates": results})

    except Exception as e:
        logger.error("ai_parsing.duplicate_search_failed", error=str(e))
        return JSONResponse(
            {"success": False, "error": f"Ошибка поиска: {str(e)}"},
            status_code=500,
        )


async def validate_event(
    request: Request,
    csrf: str = Form(...),
    event_id: str = Form(...),
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Validate and auto-fix event data."""
    require_login(request)
    check_csrf(request, csrf)

    try:
        from uuid import UUID

        # Get event
        event = await session.get(Event, UUID(event_id))
        if not event:
            return JSONResponse(
                {"success": False, "error": "Событие не найдено"},
                status_code=404,
            )

        # Convert to dict
        event_data = {
            "title": event.title,
            "date": event.date,
            "time": event.time,
            "end_time": event.end_time,
            "duration_minutes": event.duration_minutes,
            "price_min": event.price_min,
            "price_max": event.price_max,
            "capacity": event.capacity,
            "address": event.address,
        }

        # Validate
        validator = _get_validation_service()
        validated = validator.validate_event_data(event_data)

        # Find changes
        changes = []
        for key, old_value in event_data.items():
            new_value = validated.get(key)
            if old_value != new_value:
                changes.append({
                    "field": key,
                    "old_value": str(old_value),
                    "new_value": str(new_value),
                })

        logger.info("ai_parsing.event_validated", event_id=event_id, changes_count=len(changes))

        return JSONResponse({
            "success": True,
            "changes": changes,
            "validated_data": {k: str(v) if v else None for k, v in validated.items()},
        })

    except Exception as e:
        logger.error("ai_parsing.validation_failed", error=str(e))
        return JSONResponse(
            {"success": False, "error": f"Ошибка валидации: {str(e)}"},
            status_code=500,
        )


async def generate_embeddings_bulk(
    request: Request,
    csrf: str = Form(...),
    limit: int = Form(100),
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Generate embeddings for events that don't have them."""
    require_login(request)
    check_csrf(request, csrf)

    try:
        # Get events without embeddings
        stmt = select(Event).where(Event.embedding.is_(None)).limit(limit)
        result = await session.execute(stmt)
        events = result.scalars().all()

        if not events:
            return JSONResponse({
                "success": True,
                "message": "Все события уже имеют embeddings",
                "processed": 0,
            })

        # Generate embeddings
        embedding_service = _get_embedding_service()
        processed = 0
        failed = 0

        for event in events:
            try:
                embedding = embedding_service.generate_event_embedding(
                    title=event.title,
                    date=str(event.date) if event.date else None,
                    venue=event.venue_name,
                    description=event.description,
                )
                event.embedding = embedding
                processed += 1
            except Exception as e:
                logger.error("ai_parsing.embedding_generation_failed", event_id=str(event.id), error=str(e))
                failed += 1

        await session.commit()

        logger.info("ai_parsing.bulk_embeddings_generated", processed=processed, failed=failed)

        return JSONResponse({
            "success": True,
            "message": f"Обработано: {processed}, Ошибок: {failed}",
            "processed": processed,
            "failed": failed,
        })

    except Exception as e:
        logger.error("ai_parsing.bulk_generation_failed", error=str(e))
        return JSONResponse(
            {"success": False, "error": f"Ошибка генерации: {str(e)}"},
            status_code=500,
        )
