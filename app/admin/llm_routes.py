"""LLM/AI management routes for admin panel."""

from __future__ import annotations

from typing import Any
from datetime import datetime, timedelta

from fastapi import Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import LLMUsage
from app.db.session import get_session
from app.core import runtime_config as rc


def require_login(request: Request) -> None:
    """Check if user is authenticated."""
    if not request.session.get("auth") and not request.headers.get("X-Forwarded-For"):
        from fastapi import HTTPException
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
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="CSRF validation failed")


async def llm_page(request: Request, session: AsyncSession = Depends(get_session)) -> Any:
    """LLM management page with statistics and settings."""
    require_login(request)
    csrf = ensure_csrf(request)

    settings = get_settings()

    # Get current settings
    provider = rc.get("llm_provider") or "ai-mediator"
    api_key = rc.get("ai_mediator_api_key") or settings.ai_mediator_api_key or ""
    base_url = rc.get("ai_mediator_base_url") or settings.ai_mediator_base_url or "https://api.ai-mediator.ru/v1"
    model_extractor = rc.get("model_extractor") or settings.openai_model_extractor or "gpt-4o-mini"
    model_classifier = rc.get("model_classifier") or settings.openai_model_classifier or "gpt-4o-mini"
    model_summarizer = rc.get("model_summarizer") or settings.openai_model_summarizer or "gpt-4o-mini"

    # Get usage statistics
    # Total stats
    total_result = await session.execute(
        select(
            func.count(LLMUsage.id).label("count"),
            func.sum(LLMUsage.total_tokens).label("tokens"),
            func.sum(LLMUsage.cost_rub).label("cost"),
        )
    )
    total_row = total_result.first()
    total_requests = total_row.count if total_row else 0
    total_tokens = int(total_row.tokens or 0) if total_row else 0
    total_cost = float(total_row.cost or 0) if total_row else 0

    # Stats by service
    service_result = await session.execute(
        select(
            LLMUsage.service,
            func.count(LLMUsage.id).label("count"),
            func.sum(LLMUsage.prompt_tokens).label("prompt_tokens"),
            func.sum(LLMUsage.completion_tokens).label("completion_tokens"),
            func.sum(LLMUsage.total_tokens).label("total_tokens"),
        )
        .group_by(LLMUsage.service)
        .order_by(func.sum(LLMUsage.total_tokens).desc())
    )
    service_stats = [
        {
            "service": row.service,
            "count": row.count,
            "prompt_tokens": row.prompt_tokens or 0,
            "completion_tokens": row.completion_tokens or 0,
            "total_tokens": row.total_tokens or 0,
        }
        for row in service_result.all()
    ]

    # Stats by model
    model_result = await session.execute(
        select(
            LLMUsage.model,
            func.count(LLMUsage.id).label("count"),
            func.sum(LLMUsage.total_tokens).label("total_tokens"),
        )
        .group_by(LLMUsage.model)
        .order_by(func.sum(LLMUsage.total_tokens).desc())
    )
    model_stats = [
        {
            "model": row.model,
            "count": row.count,
            "total_tokens": row.total_tokens or 0,
        }
        for row in model_result.all()
    ]

    # Recent usage
    recent_result = await session.execute(
        select(LLMUsage)
        .order_by(LLMUsage.created_at.desc())
        .limit(10)
    )
    recent_usage = recent_result.scalars().all()

    # Get test result from session if exists
    test_result = request.session.pop("test_result", None)

    from fastapi.templating import Jinja2Templates
    from pathlib import Path
    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

    # Add format_number filter
    def format_number(value):
        try:
            return f"{int(value):,}".replace(",", " ")
        except (ValueError, TypeError):
            return value

    templates.env.filters["format_number"] = format_number

    return templates.TemplateResponse(
        "llm.html",
        {
            "request": request,
            "csrf": csrf,
            "provider": provider,
            "api_key": api_key[:20] + "..." if len(api_key) > 20 else api_key,
            "base_url": base_url,
            "model_extractor": model_extractor,
            "model_classifier": model_classifier,
            "model_summarizer": model_summarizer,
            "total_requests": total_requests,
            "total_tokens": total_tokens,
            "total_cost": total_cost,
            "service_stats": service_stats,
            "model_stats": model_stats,
            "recent_usage": recent_usage,
            "test_result": test_result,
        },
    )


async def llm_settings_save(
    request: Request,
    csrf: str = Form(...),
    provider: str = Form(...),
    api_key: str = Form(...),
    base_url: str = Form(...),
    model_extractor: str = Form(...),
    model_classifier: str = Form(...),
    model_summarizer: str = Form(...),
) -> Any:
    """Save LLM settings."""
    require_login(request)
    check_csrf(request, csrf)

    # Save to runtime config
    rc.set("llm_provider", provider)
    rc.set("ai_mediator_api_key", api_key)
    rc.set("ai_mediator_base_url", base_url)
    rc.set("model_extractor", model_extractor)
    rc.set("model_classifier", model_classifier)
    rc.set("model_summarizer", model_summarizer)

    return RedirectResponse("/llm?success=saved", status_code=302)


async def llm_test(request: Request, csrf: str = Form(...)) -> Any:
    """Test LLM connection."""
    require_login(request)
    check_csrf(request, csrf)

    try:
        from app.core.llm.client import chat_complete

        result = chat_complete(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Скажи 'Подключение работает!' одним предложением."}],
            temperature=0.7,
            service="test",
        )

        request.session["test_result"] = {
            "success": True,
            "message": result,
            "tokens": "~50",
        }
    except Exception as e:
        request.session["test_result"] = {
            "success": False,
            "message": f"Ошибка: {str(e)}",
        }

    return RedirectResponse("/llm", status_code=302)


async def llm_chart_data(
    request: Request,
    period: str = "7d",
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Get chart data for LLM usage visualization."""
    require_login(request)

    from fastapi.responses import JSONResponse

    # Calculate date range based on period
    now = datetime.now()
    if period == "1d":
        start_date = now - timedelta(days=1)
        date_format = "%H:%M"
    elif period == "7d":
        start_date = now - timedelta(days=7)
        date_format = "%d.%m"
    elif period == "30d":
        start_date = now - timedelta(days=30)
        date_format = "%d.%m"
    elif period == "1y":
        start_date = now - timedelta(days=365)
        date_format = "%m.%Y"
    else:
        start_date = now - timedelta(days=7)
        date_format = "%d.%m"

    # Service usage pie chart data
    service_result = await session.execute(
        select(
            LLMUsage.service,
            func.sum(LLMUsage.total_tokens).label("total_tokens"),
        )
        .where(LLMUsage.created_at >= start_date)
        .group_by(LLMUsage.service)
        .order_by(func.sum(LLMUsage.total_tokens).desc())
    )
    service_data = service_result.all()

    pie_chart = {
        "labels": [row.service for row in service_data],
        "data": [int(row.total_tokens or 0) for row in service_data],
        "backgroundColor": [
            "#FF6384",
            "#36A2EB",
            "#FFCE56",
            "#4BC0C0",
            "#9966FF",
            "#FF9F40",
        ],
    }

    # Timeline chart data (tokens over time)
    if period == "1d":
        # Hourly buckets
        time_result = await session.execute(
            select(
                func.date_trunc("hour", LLMUsage.created_at).label("time_bucket"),
                func.sum(LLMUsage.prompt_tokens).label("prompt_tokens"),
                func.sum(LLMUsage.completion_tokens).label("completion_tokens"),
            )
            .where(LLMUsage.created_at >= start_date)
            .group_by("time_bucket")
            .order_by("time_bucket")
        )
    else:
        # Daily buckets
        time_result = await session.execute(
            select(
                func.date_trunc("day", LLMUsage.created_at).label("time_bucket"),
                func.sum(LLMUsage.prompt_tokens).label("prompt_tokens"),
                func.sum(LLMUsage.completion_tokens).label("completion_tokens"),
            )
            .where(LLMUsage.created_at >= start_date)
            .group_by("time_bucket")
            .order_by("time_bucket")
        )

    time_data = time_result.all()

    timeline_chart = {
        "labels": [row.time_bucket.strftime(date_format) for row in time_data],
        "datasets": [
            {
                "label": "Prompt Tokens",
                "data": [int(row.prompt_tokens or 0) for row in time_data],
                "borderColor": "#36A2EB",
                "backgroundColor": "rgba(54, 162, 235, 0.2)",
                "tension": 0.4,
            },
            {
                "label": "Completion Tokens",
                "data": [int(row.completion_tokens or 0) for row in time_data],
                "borderColor": "#FF6384",
                "backgroundColor": "rgba(255, 99, 132, 0.2)",
                "tension": 0.4,
            },
        ],
    }

    # Model usage bar chart
    model_result = await session.execute(
        select(
            LLMUsage.model,
            func.sum(LLMUsage.total_tokens).label("total_tokens"),
        )
        .where(LLMUsage.created_at >= start_date)
        .group_by(LLMUsage.model)
        .order_by(func.sum(LLMUsage.total_tokens).desc())
    )
    model_data = model_result.all()

    bar_chart = {
        "labels": [row.model for row in model_data],
        "data": [int(row.total_tokens or 0) for row in model_data],
        "backgroundColor": "#6ea8fe",
    }

    return JSONResponse(
        {
            "pie_chart": pie_chart,
            "timeline_chart": timeline_chart,
            "bar_chart": bar_chart,
        }
    )
