"""Admin routes for monetization settings and placement management."""

from __future__ import annotations

import structlog
from fastapi import Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.services.monetization import MonetizationService
from app.db.models import MonetizationSettings, PlacementRequest, Advertiser, User
from app.db.session import get_session


logger = structlog.get_logger(module="admin.monetization")


def require_auth(request: Request) -> str:
    """Require admin authentication."""
    username = request.session.get("username")
    if not username:
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    return username


async def monetization_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    """Monetization settings and statistics page."""
    from fastapi.templating import Jinja2Templates
    from pathlib import Path

    username = require_auth(request)
    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

    # Get all monetization settings
    result = await session.execute(
        select(MonetizationSettings).order_by(MonetizationSettings.setting_key)
    )
    settings_list = result.scalars().all()

    # Convert to dict for easier template access
    settings_dict = {s.setting_key: float(s.setting_value) for s in settings_list}

    # Get placement statistics
    total_placements = await session.scalar(select(func.count(PlacementRequest.id)))
    pending_placements = await session.scalar(
        select(func.count(PlacementRequest.id)).where(PlacementRequest.status == "pending")
    )
    paid_placements = await session.scalar(
        select(func.count(PlacementRequest.id)).where(PlacementRequest.status == "paid")
    )
    active_placements = await session.scalar(
        select(func.count(PlacementRequest.id)).where(PlacementRequest.status == "active")
    )

    # Get total revenue (sum of calculated_price for paid placements)
    revenue_result = await session.execute(
        select(func.sum(PlacementRequest.calculated_price)).where(
            PlacementRequest.status.in_(["paid", "active", "completed"])
        )
    )
    total_revenue = revenue_result.scalar_one_or_none() or 0.0

    # Get user statistics for targeting
    total_users = await session.scalar(select(func.count(User.tg_id)))
    users_with_city = await session.scalar(
        select(func.count(User.tg_id)).where(User.city.isnot(None))
    )
    users_with_zone = await session.scalar(
        select(func.count(User.tg_id)).where(User.zone.isnot(None))
    )

    # Get city distribution
    city_dist_result = await session.execute(
        select(User.city, func.count(User.tg_id).label("count"))
        .where(User.city.isnot(None))
        .group_by(User.city)
        .order_by(func.count(User.tg_id).desc())
        .limit(10)
    )
    city_distribution = [{"city": row[0], "count": row[1]} for row in city_dist_result.all()]

    # Get recent placements
    recent_result = await session.execute(
        select(PlacementRequest)
        .order_by(PlacementRequest.created_at.desc())
        .limit(10)
    )
    recent_placements = recent_result.scalars().all()

    return templates.TemplateResponse(
        "monetization.html",
        {
            "request": request,
            "username": username,
            "settings": settings_dict,
            "settings_list": settings_list,
            "stats": {
                "total_placements": total_placements or 0,
                "pending_placements": pending_placements or 0,
                "paid_placements": paid_placements or 0,
                "active_placements": active_placements or 0,
                "total_revenue": float(total_revenue),
                "total_users": total_users or 0,
                "users_with_city": users_with_city or 0,
                "users_with_zone": users_with_zone or 0,
            },
            "city_distribution": city_distribution,
            "recent_placements": recent_placements,
        },
    )


async def monetization_update_setting(
    request: Request,
    setting_key: str = Form(...),
    setting_value: float = Form(...),
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    """Update a monetization setting."""
    username = require_auth(request)

    try:
        monetization = MonetizationService(session)
        await monetization.update_setting(
            key=setting_key,
            value=setting_value,
            updated_by=username,
        )

        logger.info(
            "monetization.setting_updated",
            username=username,
            key=setting_key,
            value=setting_value,
        )

        return RedirectResponse("/monetization?success=Setting updated", status_code=303)
    except Exception as e:
        logger.error("monetization.update_error", error=str(e), exc_info=True)
        return RedirectResponse(f"/monetization?error={str(e)}", status_code=303)


async def monetization_placement_approve(
    request: Request,
    placement_id: str = Form(...),
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    """Approve a pending placement request."""
    username = require_auth(request)

    try:
        import uuid
        placement_uuid = uuid.UUID(placement_id)

        result = await session.execute(
            select(PlacementRequest).where(PlacementRequest.id == placement_uuid)
        )
        placement = result.scalar_one_or_none()

        if not placement:
            raise HTTPException(status_code=404, detail="Placement not found")

        if placement.status != "pending":
            raise HTTPException(status_code=400, detail="Only pending placements can be approved")

        placement.status = "approved"
        await session.commit()

        logger.info(
            "monetization.placement_approved",
            username=username,
            placement_id=str(placement_id),
        )

        return RedirectResponse("/monetization?success=Placement approved", status_code=303)
    except Exception as e:
        logger.error("monetization.approve_error", error=str(e), exc_info=True)
        return RedirectResponse(f"/monetization?error={str(e)}", status_code=303)


async def monetization_placement_reject(
    request: Request,
    placement_id: str = Form(...),
    reject_reason: str = Form(...),
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    """Reject a pending placement request."""
    username = require_auth(request)

    try:
        import uuid
        placement_uuid = uuid.UUID(placement_id)

        result = await session.execute(
            select(PlacementRequest).where(PlacementRequest.id == placement_uuid)
        )
        placement = result.scalar_one_or_none()

        if not placement:
            raise HTTPException(status_code=404, detail="Placement not found")

        placement.status = "rejected"
        placement.reject_reason = reject_reason
        await session.commit()

        logger.info(
            "monetization.placement_rejected",
            username=username,
            placement_id=str(placement_id),
            reason=reject_reason,
        )

        return RedirectResponse("/monetization?success=Placement rejected", status_code=303)
    except Exception as e:
        logger.error("monetization.reject_error", error=str(e), exc_info=True)
        return RedirectResponse(f"/monetization?error={str(e)}", status_code=303)
