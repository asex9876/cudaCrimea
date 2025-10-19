"""Admin app (FastAPI + Jinja) with login, UGC moderation, Ads CRUD, Stats.
Includes simple session-based auth and CSRF protection.
"""

from __future__ import annotations

import json
import secrets
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Optional

import structlog
from fastapi import Depends, FastAPI, Form, HTTPException, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from redis import asyncio as aioredis
from sqlalchemy import and_, func, select
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.sessions import SessionMiddleware

import uuid
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.llm.extractor import extract_event_fields
from app.core import runtime_config as rc
from app.db.dao.events import upsert_event
from app.bot.utils.render import render_event_card
from app.db.models import Event, Place, Advertiser, PlacementRequest, UGCSubmission, AdInteraction, EditorialPin, CuratedCard, TelegramAccount, TelegramChannel
from app.db.session import get_session, get_sessionmaker
from app.admin.api_v1 import router as api_v1_router


BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
UPLOADS_DIR = BASE_DIR / "uploads"

settings = get_settings()
setup_logging(settings.log_level)
logger = structlog.get_logger(module="admin")

# Load runtime configuration from file
rc.load_from_file()

# Ensure uploads directory exists
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app = FastAPI(title=f"{settings.app_name} — Admin")
app.add_middleware(SessionMiddleware, secret_key=settings.admin_secret)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")
app.include_router(api_v1_router)

# Import Telegram routes
from app.admin import telegram_routes

# Register Telegram routes
app.get("/telegram-accounts", response_class=HTMLResponse)(telegram_routes.telegram_accounts_list)
app.post("/telegram-accounts/add")(telegram_routes.telegram_accounts_add)
app.post("/telegram-accounts/confirm")(telegram_routes.telegram_accounts_confirm)
app.post("/telegram-accounts/delete")(telegram_routes.telegram_accounts_delete)

# Import LLM routes
from app.admin import llm_routes

# Register LLM routes
app.get("/llm", response_class=HTMLResponse)(llm_routes.llm_page)
app.post("/llm/settings")(llm_routes.llm_settings_save)
app.post("/llm/test")(llm_routes.llm_test)
app.get("/llm/chart-data")(llm_routes.llm_chart_data)
app.get("/llm/prompts")(llm_routes.llm_prompts_list)
app.post("/llm/prompts/create")(llm_routes.llm_prompt_create)
app.post("/llm/prompts/{prompt_id}/update")(llm_routes.llm_prompt_update)
app.post("/llm/prompts/{prompt_id}/delete")(llm_routes.llm_prompt_delete)
app.post("/llm/prompts/{prompt_id}/set-active")(llm_routes.llm_prompt_set_active)

# Import Bot settings routes
from app.admin import bot_routes

# Register Bot settings routes
app.get("/bot/settings", response_class=HTMLResponse)(bot_routes.bot_settings_page)
app.post("/bot/settings/save")(bot_routes.bot_settings_save)
app.post("/bot/settings/apply")(bot_routes.bot_settings_apply)

# Import Telegram channel management routes
from app.admin import telegram_channel_routes

# Register Telegram channel management API routes (UI is in /parsers page)
app.post("/telegram-channels/verify")(telegram_channel_routes.verify_telegram_channel)
app.post("/telegram-channels/add")(telegram_channel_routes.add_telegram_channel)
app.post("/telegram-channels/delete")(telegram_channel_routes.delete_telegram_channel)
app.get("/telegram-channels/list")(telegram_channel_routes.list_telegram_channels)

# Import Monetization routes
from app.admin import monetization_routes

# Register Monetization routes
app.get("/monetization", response_class=HTMLResponse)(monetization_routes.monetization_page)
app.post("/monetization/update-setting")(monetization_routes.monetization_update_setting)
app.post("/monetization/placement-approve")(monetization_routes.monetization_placement_approve)
app.post("/monetization/placement-reject")(monetization_routes.monetization_placement_reject)


# ------------------ Helpers ------------------


async def get_redis() -> aioredis.Redis:
    return aioredis.from_url(str(settings.redis_url), decode_responses=True)


def require_login(request: Request) -> None:
    # Auto-authenticate if request passed through Nginx basic auth
    # Check for X-Remote-User header set by nginx after HTTP Basic Auth
    if request.headers.get("X-Remote-User"):
        # User authenticated via nginx HTTP Basic Auth - skip session check
        return

    # Fallback to session-based auth for direct access (without nginx)
    if not request.session.get("auth") and request.headers.get("X-Forwarded-For"):
        request.session["auth"] = True

    if not request.session.get("auth"):
        raise HTTPException(status_code=302, detail="redirect", headers={"Location": "/login"})


def ensure_csrf(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(16)
        request.session["csrf"] = token
    return token


def check_csrf(request: Request, token: str) -> None:
    if not token or token != request.session.get("csrf"):
        raise HTTPException(status_code=400, detail="Invalid CSRF token")


# ------------------ Routes ------------------


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> Any:
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "app_name": settings.app_name, "env": settings.env},
    )


@app.get("/settings", response_class=HTMLResponse)
async def settings_view(request: Request) -> Any:
    require_login(request)
    csrf = ensure_csrf(request)
    s = get_settings()
    current = rc.all_overrides()
    # build initial values from overrides or defaults
    ctx = {
        "request": request,
        "csrf": csrf,
        "values": {
            "app_name": current.get("app_name", s.app_name),
            # Ranking weights
            "w_time": current.get("w_time", s.w_time),
            "w_geo": current.get("w_geo", s.w_geo),
            "w_interest": current.get("w_interest", s.w_interest),
            "w_source": current.get("w_source", s.w_source),
            "w_pop": current.get("w_pop", s.w_pop),
            "w_open": current.get("w_open", s.w_open),
            # TG channels (as CSV)
            "tg_channels": ",".join(current.get("tg_channels", s.tg_channels)) if hasattr(s, "tg_channels") else ",",
            # LLM
            "ai_mediator_base_url": current.get("ai_mediator_base_url", s.ai_mediator_base_url or ""),
            "llm_auth_header": current.get("llm_auth_header", s.llm_auth_header),
            "llm_auth_scheme": current.get("llm_auth_scheme", s.llm_auth_scheme),
            # Providers
            "two_gis_api_key": "***" if rc.get("two_gis_api_key") or s.two_gis_api_key else "",
            "yandex_maps_api_key": "***" if rc.get("yandex_maps_api_key") or s.yandex_maps_api_key else "",
            # Scheduler switches
            "ingest_yandex_enabled": bool(rc.get("ingest_yandex_enabled", True)),
            "ingest_yandex_hours": rc.get("ingest_yandex_hours", 4),
            "ingest_yandex_cities": ",".join(rc.get("ingest_yandex_cities", ["Севастополь","Симферополь"])),
            "ingest_goroda_enabled": bool(rc.get("ingest_goroda_enabled", True)),
            "ingest_goroda_hours": rc.get("ingest_goroda_hours", 4),
            "ingest_goroda_cities": ",".join(rc.get("ingest_goroda_cities", ["Севастополь","Симферополь"])),
            "ingest_kassa_enabled": bool(rc.get("ingest_kassa_enabled", True)),
            "ingest_kassa_hours": rc.get("ingest_kassa_hours", 4),
            "ingest_tg_enabled": bool(rc.get("ingest_tg_enabled", True)),
            "ingest_tg_minutes": rc.get("ingest_tg_minutes", 45),
        },
    }
    return templates.TemplateResponse("settings.html", ctx)


@app.post("/settings")
async def settings_save(
    request: Request,
    csrf: str = Form(...),
    app_name: str = Form(""),
    w_time: float = Form(0.3),
    w_geo: float = Form(0.3),
    w_interest: float = Form(0.2),
    w_source: float = Form(0.1),
    w_pop: float = Form(0.1),
    w_open: float = Form(0.0),
    tg_channels: str = Form(""),
    ai_mediator_base_url: str = Form(""),
    ai_mediator_api_key: str = Form(""),
    llm_auth_header: str = Form("Authorization"),
    llm_auth_scheme: str = Form("Bearer"),
    two_gis_api_key: str = Form(""),
    yandex_maps_api_key: str = Form(""),
    # Scheduler
    ingest_yandex_enabled: str | None = Form(None),
    ingest_yandex_hours: int = Form(4),
    ingest_yandex_cities: str = Form("Севастополь,Симферополь"),
    ingest_goroda_enabled: str | None = Form(None),
    ingest_goroda_hours: int = Form(4),
    ingest_goroda_cities: str = Form("Севастополь,Симферополь"),
    ingest_kassa_enabled: str | None = Form(None),
    ingest_kassa_hours: int = Form(4),
    ingest_tg_enabled: str | None = Form(None),
    ingest_tg_minutes: int = Form(45),
) -> Any:
    require_login(request)
    check_csrf(request, csrf)
    # sanitize values
    def clamp01(x: float) -> float:
        try:
            return max(0.0, min(1.0, float(x)))
        except Exception:
            return 0.0

    overrides = {
        "app_name": app_name.strip() or get_settings().app_name,
        "w_time": clamp01(w_time),
        "w_geo": clamp01(w_geo),
        "w_interest": clamp01(w_interest),
        "w_source": clamp01(w_source),
        "w_pop": clamp01(w_pop),
        "w_open": clamp01(w_open),
        "tg_channels": [c.strip() for c in (tg_channels or "").split(",") if c.strip()],
        "ai_mediator_base_url": (ai_mediator_base_url or "").strip() or None,
        "llm_auth_header": (llm_auth_header or "Authorization").strip(),
        "llm_auth_scheme": (llm_auth_scheme or "Bearer").strip(),
    }
    if ai_mediator_api_key and ai_mediator_api_key != "***":
        overrides["ai_mediator_api_key"] = ai_mediator_api_key.strip()
    if two_gis_api_key and two_gis_api_key != "***":
        overrides["two_gis_api_key"] = two_gis_api_key.strip()
    if yandex_maps_api_key and yandex_maps_api_key != "***":
        overrides["yandex_maps_api_key"] = yandex_maps_api_key.strip()

    rc.set_many(overrides)
    # Scheduler toggles
    rc.set_many(
        {
            "ingest_yandex_enabled": bool(ingest_yandex_enabled),
            "ingest_yandex_hours": max(1, int(ingest_yandex_hours)),
            "ingest_yandex_cities": [c.strip() for c in (ingest_yandex_cities or "").split(",") if c.strip()],
            "ingest_goroda_enabled": bool(ingest_goroda_enabled),
            "ingest_goroda_hours": max(1, int(ingest_goroda_hours)),
            "ingest_goroda_cities": [c.strip() for c in (ingest_goroda_cities or "").split(",") if c.strip()],
            "ingest_kassa_enabled": bool(ingest_kassa_enabled),
            "ingest_kassa_hours": max(1, int(ingest_kassa_hours)),
            "ingest_tg_enabled": bool(ingest_tg_enabled),
            "ingest_tg_minutes": max(5, int(ingest_tg_minutes)),
        }
    )
    rc.save_to_file()
    return RedirectResponse("/settings", status_code=302)


# -------- Manual jobs trigger --------


@app.post("/jobs/run")
async def jobs_run(
    request: Request,
    csrf: str = Form(...),
    kind: str = Form(...),
    city: str | None = Form(None),
) -> Any:
    require_login(request)
    check_csrf(request, csrf)
    payload = {"kind": kind}
    if city:
        payload["city"] = city
    redis = aioredis.from_url(str(settings.redis_url), decode_responses=True)
    try:
        await redis.lpush("ingest:queue", json.dumps(payload, ensure_ascii=False))
    finally:
        await redis.aclose()
    return RedirectResponse("/settings?queued=1", status_code=302)


# -------- Parsers Management --------


@app.get("/parsers", response_class=HTMLResponse)
async def parsers_page(request: Request, session: AsyncSession = Depends(get_session)) -> Any:
    require_login(request)
    csrf = ensure_csrf(request)

    # Get parser configuration from runtime_config
    config = {
        "ingest_kudago_enabled": bool(rc.get("ingest_kudago_enabled", True)),
        "ingest_kudago_hours": rc.get("ingest_kudago_hours", 6),
        "ingest_kudago_cities": rc.get("ingest_kudago_cities", ["Севастополь", "Симферополь", "Ялта"]),

        "ingest_yandex_enabled": bool(rc.get("ingest_yandex_enabled", True)),
        "ingest_yandex_hours": rc.get("ingest_yandex_hours", 4),
        "ingest_yandex_cities": rc.get("ingest_yandex_cities", ["Севастополь", "Симферополь"]),

        "ingest_goroda_enabled": bool(rc.get("ingest_goroda_enabled", True)),
        "ingest_goroda_hours": rc.get("ingest_goroda_hours", 4),
        "ingest_goroda_cities": rc.get("ingest_goroda_cities", ["Севастополь", "Симферополь"]),

        "ingest_tg_enabled": bool(rc.get("ingest_tg_enabled", True)),
        "ingest_tg_minutes": rc.get("ingest_tg_minutes", 45),
        "ingest_tg_days": rc.get("ingest_tg_days", 7),
        "ingest_tg_channels_text": rc.get("ingest_tg_channels_text", "simferopol_afisha\nyalta_afisha\nsevastopol_events\ncrimea_events\nkrym_afisha"),
        "tg_parser_status": rc.get("tg_parser_status", "enabled"),
        "tg_api_id": rc.get("tg_api_id", settings.tg_api_id or ""),
        "tg_api_hash": rc.get("tg_api_hash", settings.tg_api_hash),
        "tg_api_hash_masked": "••••••••" if rc.get("tg_api_hash") or settings.tg_api_hash else "",
    }

    # Calculate statistics
    from datetime import datetime, timedelta

    # Total events
    total_events_result = await session.execute(select(func.count(Event.id)))
    total_events = total_events_result.scalar_one()

    # Active events (status = active)
    active_events_result = await session.execute(
        select(func.count(Event.id)).where(Event.status == "active")
    )
    active_events = active_events_result.scalar_one()

    # Events added today
    today = datetime.now().date()
    today_events_result = await session.execute(
        select(func.count(Event.id)).where(func.date(Event.created_at) == today)
    )
    today_events = today_events_result.scalar_one()

    # Events by source (count unique sources)
    sources_result = await session.execute(
        select(func.count(func.distinct(Event.source)))
    )
    sources_count = sources_result.scalar_one()

    stats = {
        "total_events": total_events,
        "active_events": active_events,
        "today_events": today_events,
        "sources_count": sources_count,
    }

    # Get active Telegram accounts
    tg_accounts = (await session.execute(
        select(TelegramAccount)
        .where(TelegramAccount.status == "active")
        .order_by(TelegramAccount.created_at.desc())
    )).scalars().all()

    # Get selected account ID from config
    selected_tg_account_id = rc.get("tg_account_id")

    # Get Telegram channels from database
    channels = (await session.execute(
        select(TelegramChannel).order_by(TelegramChannel.added_at.desc())
    )).scalars().all()

    return templates.TemplateResponse(
        "parsers.html",
        {
            "request": request,
            "csrf": csrf,
            "config": config,
            "stats": stats,
            "tg_accounts": tg_accounts,
            "selected_tg_account_id": selected_tg_account_id,
            "channels": channels,
        }
    )


@app.post("/parsers/settings")
async def save_parser_settings(
    request: Request,
    csrf: str = Form(...),
    # KudaGo
    kudago_enabled: str | None = Form(None),
    kudago_hours: int = Form(6),
    kudago_cities: str = Form("Севастополь,Симферополь,Ялта"),
    # Yandex
    yandex_enabled: str | None = Form(None),
    yandex_hours: int = Form(4),
    yandex_cities: str = Form("Севастополь,Симферополь"),
    # Goroda
    goroda_enabled: str | None = Form(None),
    goroda_hours: int = Form(4),
    goroda_cities: str = Form("Севастополь,Симферополь"),
    # Telegram
    tg_enabled: str | None = Form(None),
    tg_minutes: int = Form(45),
    tg_days: int = Form(7),
    tg_channels: str = Form("simferopol_afisha,yalta_afisha,sevastopol_events"),
    tg_account_id: str | None = Form(None),
) -> Any:
    require_login(request)
    check_csrf(request, csrf)

    # Parse city lists
    kudago_cities_list = [c.strip() for c in kudago_cities.split(",") if c.strip()]
    yandex_cities_list = [c.strip() for c in yandex_cities.split(",") if c.strip()]
    goroda_cities_list = [c.strip() for c in goroda_cities.split(",") if c.strip()]

    # Parse TG channels (one per line or comma-separated)
    tg_channels_list = []
    for line in tg_channels.split("\n"):
        line = line.strip()
        if line:
            # Remove @ if present
            if line.startswith("@"):
                line = line[1:]
            tg_channels_list.append(line)

    # Save to runtime config
    config_data = {
        "ingest_kudago_enabled": bool(kudago_enabled),
        "ingest_kudago_hours": max(1, int(kudago_hours)),
        "ingest_kudago_cities": kudago_cities_list,

        "ingest_yandex_enabled": bool(yandex_enabled),
        "ingest_yandex_hours": max(1, int(yandex_hours)),
        "ingest_yandex_cities": yandex_cities_list,

        "ingest_goroda_enabled": bool(goroda_enabled),
        "ingest_goroda_hours": max(1, int(goroda_hours)),
        "ingest_goroda_cities": goroda_cities_list,

        "ingest_tg_enabled": bool(tg_enabled),
        "ingest_tg_minutes": max(5, int(tg_minutes)),
        "ingest_tg_days": max(1, int(tg_days)),
        "ingest_tg_channels": tg_channels_list,
        "ingest_tg_channels_text": "\n".join(tg_channels_list),
    }

    # Add selected Telegram account ID if provided
    if tg_account_id:
        config_data["tg_account_id"] = tg_account_id

    rc.set_many(config_data)

    rc.save_to_file()
    logger.info("parsers.settings.saved")

    return {"success": True, "message": "Настройки успешно сохранены"}


@app.post("/parsers/run/{parser}")
async def run_parser_manually(
    parser: str,
    request: Request,
    csrf: str = Form(...),
    session: AsyncSession = Depends(get_session),
) -> Any:
    require_login(request)
    check_csrf(request, csrf)

    count = 0

    try:
        if parser == "kudago":
            from app.ingestors import kudago
            cities = rc.get("ingest_kudago_cities", ["Севастополь", "Симферополь", "Ялта"])
            for city in cities:
                cnt = await kudago.ingest(city, session)
                count += cnt
            logger.info("parsers.run.kudago", count=count)

        elif parser == "yandex":
            try:
                from app.ingestors import yandex_afisha
                cities = rc.get("ingest_yandex_cities", ["Севастополь", "Симферополь"])
                for city in cities:
                    cnt = await yandex_afisha.ingest(city, session)
                    count += cnt
                logger.info("parsers.run.yandex", count=count)
            except ImportError:
                raise HTTPException(status_code=400, detail="Yandex parser requires playwright (not installed)")

        elif parser == "goroda":
            try:
                from app.ingestors import afisha_goroda
                cities = rc.get("ingest_goroda_cities", ["Севастополь", "Симферополь"])
                for city in cities:
                    cnt = await afisha_goroda.ingest(city, session)
                    count += cnt
                logger.info("parsers.run.goroda", count=count)
            except ImportError:
                raise HTTPException(status_code=400, detail="Goroda parser requires playwright (not installed)")

        elif parser == "kassa24":
            from app.ingestors import kassa24
            count = await kassa24.ingest(session)
            logger.info("parsers.run.kassa24", count=count)

        elif parser == "afisha82":
            from app.ingestors import afisha82_ru
            count = await afisha82_ru.ingest(session)
            logger.info("parsers.run.afisha82", count=count)

        elif parser == "kassa24":
            from app.ingestors import sevastopol_kassa24
            count = await sevastopol_kassa24.ingest(session)
            logger.info("parsers.run.kassa24", count=count)

        elif parser == "culture":
            from app.ingestors import culture_ru
            count = await culture_ru.ingest(session)
            logger.info("parsers.run.culture", count=count)

        elif parser == "afisha_ru":
            from app.ingestors import afisha_ru_sevastopol
            count = await afisha_ru_sevastopol.ingest(session)
            logger.info("parsers.run.afisha_ru", count=count)

        elif parser == "tg":
            from app.ingestors import telegram_channels
            days = rc.get("ingest_tg_days", 7)
            count = await telegram_channels.ingest(session, limit_days=days)
            logger.info("parsers.run.telegram", count=count, days=days)

        else:
            return {"success": False, "error": "Unknown parser", "parser": parser}

        return {"success": True, "count": count, "parser": parser}

    except Exception as e:
        logger.error("parsers.run.error", parser=parser, error=str(e))
        return {"success": False, "error": str(e), "parser": parser}


@app.post("/parsers/run-all")
async def run_all_parsers(
    request: Request,
    csrf: str = Form(...),
    session: AsyncSession = Depends(get_session),
) -> Any:
    require_login(request)
    check_csrf(request, csrf)

    total_count = 0
    results = []

    try:
        # KudaGo
        if rc.get("ingest_kudago_enabled", True):
            from app.ingestors import kudago
            cities = rc.get("ingest_kudago_cities", ["Севастополь", "Симферополь", "Ялта"])
            count = 0
            for city in cities:
                cnt = await kudago.ingest(city, session)
                count += cnt
            total_count += count
            results.append(f"KudaGo: {count}")

        # Yandex
        if rc.get("ingest_yandex_enabled", True):
            try:
                from app.ingestors import yandex_afisha
                cities = rc.get("ingest_yandex_cities", ["Севастополь", "Симферополь"])
                count = 0
                for city in cities:
                    cnt = await yandex_afisha.ingest(city, session)
                    count += cnt
                total_count += count
                results.append(f"Yandex: {count}")
            except ImportError:
                results.append("Yandex: skipped (playwright not installed)")

        # Afisha Goroda
        if rc.get("ingest_goroda_enabled", True):
            try:
                from app.ingestors import afisha_goroda
                cities = rc.get("ingest_goroda_cities", ["Севастополь", "Симферополь"])
                count = 0
                for city in cities:
                    cnt = await afisha_goroda.ingest(city, session)
                    count += cnt
                total_count += count
                results.append(f"Goroda: {count}")
            except ImportError:
                results.append("Goroda: skipped (playwright not installed)")

        # Kassa24
        if rc.get("ingest_kassa_enabled", True):
            from app.ingestors import kassa24
            count = await kassa24.ingest(session)
            total_count += count
            results.append(f"Kassa24: {count}")

        # Telegram
        if rc.get("ingest_tg_enabled", True):
            from app.ingestors import telegram_channels
            days = rc.get("ingest_tg_days", 7)
            count = await telegram_channels.ingest(session, limit_days=days)
            total_count += count
            results.append(f"Telegram: {count}")

        logger.info("parsers.run.all", total=total_count, results=results)
        return {"success": True, "total_count": total_count, "results": results}

    except Exception as e:
        logger.error("parsers.run.all.error", error=str(e))
        return {"success": False, "error": str(e)}


@app.post("/parsers/tg-status")
async def set_telegram_parser_status(
    request: Request,
    csrf: str = Form(...),
    status: str = Form(...),
) -> Any:
    """Set Telegram parser status (enabled/waiting/disabled)."""
    require_login(request)
    check_csrf(request, csrf)

    # Validate status
    if status not in ("enabled", "waiting", "disabled"):
        from fastapi.responses import JSONResponse
        return JSONResponse(
            {"success": False, "error": "Неверный статус. Доступны: enabled, waiting, disabled"},
            status_code=400
        )

    # Save status to runtime config
    rc.set("tg_parser_status", status)
    rc.save_to_file()

    logger.info("telegram.parser.status.changed", status=status)

    from fastapi.responses import JSONResponse
    return JSONResponse({"success": True, "status": status})


# -------- Events CRUD --------


@app.get("/events", response_class=HTMLResponse)
async def events_list(
    request: Request,
    session: AsyncSession = Depends(get_session),
    city: str | None = None,
    category: str | None = None,
    sort: str = "desc",
    status: str | None = None
) -> Any:
    require_login(request)
    csrf = ensure_csrf(request)

    # Build query with filters
    query = select(Event)

    if city:
        query = query.where(Event.city == city)
    if category:
        query = query.where(Event.category == category)
    if status:
        query = query.where(Event.status == status)

    # Apply sorting
    if sort == "asc":
        query = query.order_by(Event.date.asc(), Event.time.asc())
    else:
        query = query.order_by(Event.date.desc(), Event.time.desc())

    query = query.limit(500)
    rows = (await session.execute(query)).scalars().all()

    # Get unique cities from database
    cities_query = select(Event.city).distinct().where(Event.city.isnot(None))
    cities_result = (await session.execute(cities_query)).scalars().all()
    cities = sorted([c for c in cities_result if c])

    # Categories with labels
    categories = [
        ("🎵 Концерты", "concert"),
        ("🎭 Театр", "theatre"),
        ("👶 Детям", "kids"),
        ("🗺 Экскурсии", "tour"),
        ("🎉 Вечеринки", "party"),
        ("🎨 Выставки", "expo"),
        ("📌 Другое", "other"),
    ]

    return templates.TemplateResponse("events_list.html", {
        "request": request,
        "csrf": csrf,
        "items": rows,
        "cities": cities,
        "categories": categories
    })


@app.get("/events/new", response_class=HTMLResponse)
async def events_new(request: Request) -> Any:
    require_login(request)
    csrf = ensure_csrf(request)
    return templates.TemplateResponse("events_edit.html", {"request": request, "csrf": csrf, "item": None})


@app.get("/events/{event_id}", response_class=HTMLResponse)
async def events_edit(event_id: str, request: Request, session: AsyncSession = Depends(get_session)) -> Any:
    require_login(request)
    csrf = ensure_csrf(request)
    item = await session.get(Event, event_id)
    if not item:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("events_edit.html", {"request": request, "csrf": csrf, "item": item})


@app.post("/events/save")
async def events_save(
    request: Request,
    csrf: str = Form(...),
    id: str | None = Form(None),
    title: str = Form(...),
    date: date = Form(...),
    time: str | None = Form(None),
    city: str | None = Form(None),
    price_min: int | None = Form(None),
    price_max: int | None = Form(None),
    category: str = Form("other"),
    venue_name: str = Form(""),
    address: str | None = Form(None),
    lat: float | None = Form(None),
    lon: float | None = Form(None),
    source: str = Form("editor"),
    source_url: str = Form(""),
    quality_score: float = Form(0.5),
    image_file: UploadFile | None = File(None),
    image_url_field: str | None = Form(None),
    session: AsyncSession = Depends(get_session),
) -> Any:
    require_login(request)
    check_csrf(request, csrf)
    from datetime import time as dtime

    try:
        tval = dtime.fromisoformat(time) if time else None
        # Handle image upload
        final_image_url = image_url_field.strip() if image_url_field else None
        if image_file and image_file.filename:
            uploads = STATIC_DIR / "uploads"
            uploads.mkdir(parents=True, exist_ok=True)
            ext = Path(image_file.filename).suffix or ".jpg"
            fname = f"ev_{uuid.uuid4().hex}{ext}"
            dest = uploads / fname
            with dest.open("wb") as f:
                f.write(await image_file.read())
            final_image_url = f"/static/uploads/{fname}"

        if id:
            ev = await session.get(Event, id)
            if not ev:
                raise HTTPException(status_code=404)
            ev.title = title
            ev.date = date
            ev.time = tval
            ev.city = city
            ev.price_min = price_min
            ev.price_max = price_max
            ev.category = category
            ev.venue_name = venue_name
            ev.address = address or ""
            ev.lat = lat
            ev.lon = lon
            ev.source = source
            ev.source_url = source_url
            ev.quality_score = quality_score
            ev.image_url = final_image_url
        else:
            from app.db.models.tables import Event as Ev

            ev = Ev(
                title=title,
                date=date,
                time=tval,
                city=city,
                price_min=price_min,
                price_max=price_max,
                category=category,
                venue_name=venue_name,
                address=address or "",
                lat=lat,
                lon=lon,
                source=source,
                source_url=source_url,
                quality_score=quality_score,
                image_url=final_image_url,
            )
            session.add(ev)
        await session.commit()
        return RedirectResponse("/events", status_code=302)
    except Exception as e:  # noqa: BLE001
        # Show form again with error message
        csrf = ensure_csrf(request)
        item = None
        try:
            # If editing existing, load to prefill
            if id:
                item = await session.get(Event, id)
        except Exception:
            item = None
        return templates.TemplateResponse(
            "events_edit.html",
            {
                "request": request,
                "csrf": csrf,
                "item": item,
                "error": f"Ошибка сохранения: {str(e)}",
            },
            status_code=400,
        )


@app.post("/events/{event_id}/delete")
async def events_delete(event_id: str, request: Request, csrf: str = Form(...), session: AsyncSession = Depends(get_session)) -> Any:
    require_login(request)
    check_csrf(request, csrf)
    ev = await session.get(Event, event_id)
    if ev:
        await session.delete(ev)
        await session.commit()
        from fastapi.responses import JSONResponse
        return JSONResponse({"success": True, "message": "Событие успешно удалено"})
    from fastapi.responses import JSONResponse
    return JSONResponse({"success": False, "error": "Событие не найдено"}, status_code=404)


# -------- Places CRUD --------


@app.get("/places", response_class=HTMLResponse)
async def places_list(request: Request, session: AsyncSession = Depends(get_session)) -> Any:
    require_login(request)
    csrf = ensure_csrf(request)
    rows = (await session.execute(select(Place).order_by(Place.created_at.desc()).limit(200))).scalars().all()
    return templates.TemplateResponse("places_list.html", {"request": request, "csrf": csrf, "items": rows})


@app.get("/places/new", response_class=HTMLResponse)
async def places_new(request: Request) -> Any:
    require_login(request)
    csrf = ensure_csrf(request)
    return templates.TemplateResponse("places_edit.html", {"request": request, "csrf": csrf, "item": None})


@app.get("/places/{place_id}", response_class=HTMLResponse)
async def places_edit(place_id: str, request: Request, session: AsyncSession = Depends(get_session)) -> Any:
    require_login(request)
    csrf = ensure_csrf(request)
    item = await session.get(Place, place_id)
    if not item:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("places_edit.html", {"request": request, "csrf": csrf, "item": item})


@app.post("/places/save")
async def places_save(
    request: Request,
    csrf: str = Form(...),
    id: str | None = Form(None),
    name: str = Form(...),
    category: str = Form("other"),
    address: str = Form(""),
    lat: float = Form(...),
    lon: float = Form(...),
    phone: str | None = Form(None),
    hours: str | None = Form(None),
    rating: float | None = Form(None),
    price_level: int | None = Form(None),
    source: str = Form("editor"),
    external_id: str = Form(""),
    image_file: UploadFile | None = File(None),
    image_url_field: str | None = Form(None),
    session: AsyncSession = Depends(get_session),
) -> Any:
    require_login(request)
    check_csrf(request, csrf)
    import json

    hours_json = None
    final_image_url = image_url_field.strip() if image_url_field else None
    if image_file and image_file.filename:
        uploads = STATIC_DIR / "uploads"
        uploads.mkdir(parents=True, exist_ok=True)
        ext = Path(image_file.filename).suffix or ".jpg"
        fname = f"pl_{uuid.uuid4().hex}{ext}"
        dest = uploads / fname
        with dest.open("wb") as f:
            f.write(await image_file.read())
        final_image_url = f"/static/uploads/{fname}"
    if hours:
        try:
            hours_json = json.loads(hours)
        except json.JSONDecodeError:
            hours_json = None
    if id:
        pl = await session.get(Place, id)
        if not pl:
            raise HTTPException(status_code=404)
        pl.name = name
        pl.category = category
        pl.address = address
        pl.lat = lat
        pl.lon = lon
        pl.phone = phone
        pl.hours = hours_json
        pl.rating = rating
        pl.price_level = price_level
        pl.source = source
        pl.external_id = external_id
        pl.image_url = final_image_url
    else:
        from app.db.models.tables import Place as Pl

        pl = Pl(
            name=name,
            category=category,
            address=address,
            lat=lat,
            lon=lon,
            phone=phone,
            hours=hours_json,
            rating=rating,
            price_level=price_level,
            source=source,
            external_id=external_id,
            image_url=final_image_url,
        )
        session.add(pl)
    await session.commit()
    return RedirectResponse("/places", status_code=302)


@app.post("/places/{place_id}/delete")
async def places_delete(place_id: str, request: Request, csrf: str = Form(...), session: AsyncSession = Depends(get_session)) -> Any:
    require_login(request)
    check_csrf(request, csrf)
    pl = await session.get(Place, place_id)
    if pl:
        await session.delete(pl)
        await session.commit()
        from fastapi.responses import JSONResponse
        return JSONResponse({"success": True, "message": "Место успешно удалено"})
    from fastapi.responses import JSONResponse
    return JSONResponse({"success": False, "error": "Место не найдено"}, status_code=404)


# -------- Editorial Pins CRUD --------


@app.get("/pins", response_class=HTMLResponse)
async def pins_list(request: Request, session: AsyncSession = Depends(get_session)) -> Any:
    require_login(request)
    csrf = ensure_csrf(request)
    rows = (await session.execute(select(EditorialPin).order_by(EditorialPin.priority.desc()).limit(200))).scalars().all()
    return templates.TemplateResponse("pins_list.html", {"request": request, "csrf": csrf, "items": rows})


@app.get("/pins/new", response_class=HTMLResponse)
async def pins_new(request: Request) -> Any:
    require_login(request)
    csrf = ensure_csrf(request)
    return templates.TemplateResponse("pins_edit.html", {"request": request, "csrf": csrf, "item": None})


@app.get("/pins/{pin_id}", response_class=HTMLResponse)
async def pins_edit(pin_id: str, request: Request, session: AsyncSession = Depends(get_session)) -> Any:
    require_login(request)
    csrf = ensure_csrf(request)
    item = await session.get(EditorialPin, pin_id)
    if not item:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("pins_edit.html", {"request": request, "csrf": csrf, "item": item})


@app.post("/pins/save")
async def pins_save(
    request: Request,
    csrf: str = Form(...),
    id: str | None = Form(None),
    item_type: str = Form(...),
    item_id: str = Form(...),
    title_override: str | None = Form(None),
    city: str = Form(...),
    active_from: date = Form(...),
    active_to: date = Form(...),
    priority: int = Form(0),
    session: AsyncSession = Depends(get_session),
) -> Any:
    require_login(request)
    check_csrf(request, csrf)
    if id:
        pin = await session.get(EditorialPin, id)
        if not pin:
            raise HTTPException(status_code=404)
        pin.item_type = item_type
        pin.item_id = uuid.UUID(item_id)
        pin.title_override = title_override
        pin.city = city
        pin.active_from = active_from
        pin.active_to = active_to
        pin.priority = int(priority)
    else:
        from uuid import uuid4

        pin = EditorialPin(
            id=uuid4(),
            item_type=item_type,
            item_id=uuid.UUID(item_id),
            title_override=title_override,
            city=city,
            active_from=active_from,
            active_to=active_to,
            priority=int(priority),
        )
        session.add(pin)
    await session.commit()
    return RedirectResponse("/pins", status_code=302)


@app.post("/pins/{pin_id}/delete")
async def pins_delete(pin_id: str, request: Request, csrf: str = Form(...), session: AsyncSession = Depends(get_session)) -> Any:
    require_login(request)
    check_csrf(request, csrf)
    pin = await session.get(EditorialPin, pin_id)
    if pin:
        await session.delete(pin)
        await session.commit()
        from fastapi.responses import JSONResponse
        return JSONResponse({"success": True, "message": "Пин успешно удалён"})
    from fastapi.responses import JSONResponse
    return JSONResponse({"success": False, "error": "Пин не найден"}, status_code=404)


# -------- Curated Cards CRUD --------


@app.get("/cards", response_class=HTMLResponse)
async def cards_list(request: Request, session: AsyncSession = Depends(get_session)) -> Any:
    require_login(request)
    csrf = ensure_csrf(request)
    rows = (await session.execute(select(CuratedCard).order_by(CuratedCard.priority.desc()).limit(200))).scalars().all()
    return templates.TemplateResponse("cards_list.html", {"request": request, "csrf": csrf, "items": rows})


@app.get("/cards/new", response_class=HTMLResponse)
async def cards_new(request: Request) -> Any:
    require_login(request)
    csrf = ensure_csrf(request)
    return templates.TemplateResponse("cards_edit.html", {"request": request, "csrf": csrf, "item": None})


@app.get("/cards/{card_id}", response_class=HTMLResponse)
async def cards_edit(card_id: str, request: Request, session: AsyncSession = Depends(get_session)) -> Any:
    require_login(request)
    csrf = ensure_csrf(request)
    item = await session.get(CuratedCard, card_id)
    if not item:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("cards_edit.html", {"request": request, "csrf": csrf, "item": item})


@app.post("/cards/save")
async def cards_save(
    request: Request,
    csrf: str = Form(...),
    id: str | None = Form(None),
    item_type: str = Form(...),
    ref_id: str | None = Form(None),
    title: str = Form(...),
    subtitle: str | None = Form(None),
    category: str | None = Form(None),
    city: str | None = Form(None),
    address: str | None = Form(None),
    lat: float | None = Form(None),
    lon: float | None = Form(None),
    button_url: str | None = Form(None),
    active_from: date = Form(...),
    active_to: date = Form(...),
    priority: int = Form(0),
    is_active: str | None = Form(None),
    image_file: UploadFile | None = File(None),
    image_url_field: str | None = Form(None),
    session: AsyncSession = Depends(get_session),
) -> Any:
    require_login(request)
    check_csrf(request, csrf)
    # handle image
    final_image_url = image_url_field.strip() if image_url_field else None
    if image_file and image_file.filename:
        uploads = STATIC_DIR / "uploads"
        uploads.mkdir(parents=True, exist_ok=True)
        ext = Path(image_file.filename).suffix or ".jpg"
        fname = f"card_{uuid.uuid4().hex}{ext}"
        dest = uploads / fname
        with dest.open("wb") as f:
            f.write(await image_file.read())
        final_image_url = f"/static/uploads/{fname}"

    ref_uuid = None
    if ref_id:
        try:
            ref_uuid = uuid.UUID(ref_id)
        except Exception:
            ref_uuid = None

    if id:
        card = await session.get(CuratedCard, id)
        if not card:
            raise HTTPException(status_code=404)
        card.item_type = item_type
        card.ref_id = ref_uuid
        card.title = title
        card.subtitle = subtitle
        card.category = category
        card.city = city
        card.address = address
        card.lat = lat
        card.lon = lon
        card.button_url = button_url
        card.active_from = active_from
        card.active_to = active_to
        card.priority = int(priority)
        card.is_active = bool(is_active)
        card.image_url = final_image_url
    else:
        from uuid import uuid4

        card = CuratedCard(
            id=uuid4(),
            item_type=item_type,
            ref_id=ref_uuid,
            title=title,
            subtitle=subtitle,
            category=category,
            city=city,
            address=address,
            lat=lat,
            lon=lon,
            button_url=button_url,
            image_url=final_image_url,
            active_from=active_from,
            active_to=active_to,
            priority=int(priority),
            is_active=bool(is_active),
        )
        session.add(card)
    await session.commit()
    return RedirectResponse("/cards", status_code=302)


@app.post("/cards/{card_id}/delete")
async def cards_delete(card_id: str, request: Request, csrf: str = Form(...), session: AsyncSession = Depends(get_session)) -> Any:
    require_login(request)
    check_csrf(request, csrf)
    card = await session.get(CuratedCard, card_id)
    if card:
        await session.delete(card)
        await session.commit()
        from fastapi.responses import JSONResponse
        return JSONResponse({"success": True, "message": "Карточка успешно удалена"})
    from fastapi.responses import JSONResponse
    return JSONResponse({"success": False, "error": "Карточка не найдена"}, status_code=404)


# -------- Demo seed via admin --------


@app.post("/seed/demo")
async def seed_demo(request: Request, csrf: str = Form(...), session: AsyncSession = Depends(get_session)) -> Any:
    require_login(request)
    check_csrf(request, csrf)
    # Use same generator as script
    from app.scripts.seed_demo_events import _samples_for_city
    from sqlalchemy import insert

    rows = []
    for city in ("Севастополь", "Симферополь"):
        rows.extend(_samples_for_city(city))
    if rows:
        await session.execute(insert(Event).values(rows))
        await session.commit()
    return RedirectResponse("/events", status_code=302)


@app.get("/login", response_class=HTMLResponse)
async def admin_login_form(request: Request) -> Any:
    csrf = ensure_csrf(request)
    return templates.TemplateResponse("login.html", {"request": request, "csrf": csrf})


@app.post("/login")
async def admin_login(request: Request, username: str = Form(""), password: str = Form(""), token: str = Form(""), csrf: str = Form("")) -> Any:
    check_csrf(request, csrf)
    ok = False
    if settings.admin_token and token == settings.admin_token:
        ok = True
    elif settings.admin_user and settings.admin_password and username == settings.admin_user and password == settings.admin_password:
        ok = True
    if not ok:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Неверные данные", "csrf": ensure_csrf(request)}, status_code=400)
    request.session["auth"] = True
    return RedirectResponse("/", status_code=302)


@app.get("/logout")
async def admin_logout(request: Request) -> Any:
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


# -------- UGC moderation --------


@app.get("/ugc", response_class=HTMLResponse)
async def ugc_list(request: Request, queue: str = "all", redis: aioredis.Redis = Depends(get_redis)) -> Any:
    require_login(request)
    csrf = ensure_csrf(request)

    # DEBUG: Check if route is being called
    logger.info("ugc_route_called", queue=queue, user=request.headers.get("X-Remote-User"))

    # Fetch from queues based on filter
    items_raw = []
    if queue == "all":
        items_raw.extend(await redis.lrange("ugc:queue", 0, 199))
        items_raw.extend(await redis.lrange("ugc:queue:paid", 0, 199))
        items_raw.extend(await redis.lrange("ugc:queue:parser", 0, 199))
    elif queue == "free":
        items_raw.extend(await redis.lrange("ugc:queue", 0, 199))
    elif queue == "paid":
        items_raw.extend(await redis.lrange("ugc:queue:paid", 0, 199))
    elif queue == "parser":
        items_raw.extend(await redis.lrange("ugc:queue:parser", 0, 199))

    items = items_raw
    enriched: list[dict[str, Any]] = []
    for raw in items:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {"raw_text": raw}
        # Extract optional structured form fields for readable preview
        form = data.get("form") if isinstance(data, dict) else None
        # Fallback: sometimes bots sent form only inside raw_text as "FORM:{...}" (string)
        if not form and isinstance(data.get("raw_text"), str):
            rt = data.get("raw_text", "")
            if rt.startswith("FORM:"):
                raw_form = rt.split("FORM:", 1)[1].strip()
                # Try JSON load; if it looks like python dict with single quotes/None, normalize
                try:
                    form = json.loads(raw_form)
                except json.JSONDecodeError:
                    try:
                        norm = raw_form.replace("'", '"').replace(": None", ": null").replace(": None,", ": null,")
                        form = json.loads(norm)
                    except Exception:
                        form = None
        images = []
        if isinstance(data.get("images"), list):
            images = [str(u) for u in data.get("images") if isinstance(u, str)]
        elif isinstance(data.get("image_url"), str) and data.get("image_url"):
            images = [str(data.get("image_url"))]
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
            "source_url": data.get("source_url"),
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
                "source_url": form.get("source_url") or data.get("source_url"),
            })
        # Build bot-like caption using the same renderer as in the bot
        class _E:
            ...
        eobj = _E()
        setattr(eobj, "title", preview.get("title"))
        setattr(eobj, "category", preview.get("category"))
        setattr(eobj, "venue_name", preview.get("venue_name") or "")
        setattr(eobj, "address", preview.get("address") or "")
        setattr(eobj, "date", preview.get("date_iso") or "")
        # bot renderer expects `time`
        setattr(eobj, "time", preview.get("time_24h") or None)
        setattr(eobj, "price_min", preview.get("price_min"))
        setattr(eobj, "price_max", preview.get("price_max"))
        caption_text = render_event_card(eobj)
        if preview.get("source_url"):
            caption_text = caption_text + f"\nСайт: {preview.get('source_url')}"

        # Build static Telegram-like buttons preview
        tg_buttons: list[dict[str, str]] = []
        src = str(preview.get("source_url") or "").strip()
        if src:
            tg_buttons.append({"text": "Сайт", "url": src})
            if preview.get("price_min") is not None or preview.get("price_max") is not None:
                tg_buttons.append({"text": "Билеты", "url": src})
        # split buttons into rows to mimic Telegram layout (max 2 per row)
        rows: list[list[dict[str, str]]] = []
        row: list[dict[str, str]] = []
        for b in tg_buttons:
            row.append(b)
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)

        enriched.append(
            {
                "raw": raw,
                "id": secrets.token_hex(8),
                "raw_text": data.get("raw_text", raw),
                "source_url": preview.get("source_url"),
                "images": images,
                "preview": preview,
                "caption": caption_text,
                "tg_buttons": tg_buttons,
                "tg_buttons_rows": rows,
                "user_id": data.get("user_id"),
                "ts": data.get("ts"),
                "wants_paid_promotion": data.get("wants_paid_promotion", False),
                "is_parser": data.get("source") == "parser",  # Mark parsed events
                "parser_name": data.get("parser_name", ""),  # Parser source name
                "is_ai_processed": isinstance(form, dict) and form is not None,  # Mark AI-processed items
            }
        )
    return templates.TemplateResponse("ugc.html", {"request": request, "csrf": csrf, "items": enriched, "current_queue": queue})


@app.post("/ugc/approve")
async def ugc_approve(request: Request, raw: str = Form(...), csrf: str = Form(...), session: AsyncSession = Depends(get_session), redis: aioredis.Redis = Depends(get_redis)) -> Any:
    require_login(request)
    check_csrf(request, csrf)
    # Parse
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {"raw_text": raw}
    raw_text = data.get("raw_text", "")
    source_url = data.get("source_url")
    # Prefer structured form if present; otherwise extract via LLM
    form = data.get("form") if isinstance(data, dict) else None
    if form and isinstance(form, dict):
        from app.core.llm.extractor import EventDraft

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
        # City is not part of EventDraft; we don't store it directly in Event
        lat = form.get("lat")
        lon = form.get("lon")
    else:
        draft = extract_event_fields(raw_text, source_url)
        lat = None
        lon = None
    if not draft.title or not draft.date_iso:
        return RedirectResponse("/ugc?error=invalid", status_code=302)

    # Upsert into events
    from datetime import datetime as _dt
    from datetime import date as _date
    from datetime import time as _time

    dt = _dt.fromisoformat(draft.date_iso + ("T" + (draft.time_24h or "00:00") + ":00"))
    city_from_form = form.get("city") if form else None
    ev = await upsert_event(
        session,
        title=draft.title,
        date_=_date.fromisoformat(draft.date_iso),
        time_=_time.fromisoformat(draft.time_24h) if draft.time_24h else None,
        city=city_from_form,
        venue_name=draft.venue_name or "",
        address=draft.address,
        lat=lat,
        lon=lon,
        price_min=draft.price_min,
        price_max=draft.price_max,
        category=draft.category or "other",
        source="ugc",
        source_url=draft.source_url or (source_url or ""),
        quality_base=0.5,
    )
    # Attach optional images from queue payload
    img_url = data.get("image_url")
    images = data.get("images") if isinstance(data, dict) else None
    final_img = None
    if images and isinstance(images, list) and images:
        final_img = images[0]
    elif img_url:
        final_img = img_url
    if final_img:
        ev.image_url = final_img

    # Save images JSON array for admin panel display (JSONB auto-serializes, don't use json.dumps!)
    if images and isinstance(images, list) and images:
        ev.images = images

    # Save gallery in separate table
    from app.db.models import EventImage
    if images and isinstance(images, list):
        # clear previous
        await session.execute(sa.delete(EventImage).where(EventImage.event_id == ev.id))
        for i, url in enumerate(images):
            session.add(EventImage(event_id=ev.id, url=url, priority=i))
    await session.commit()

    # Remove from all queues (try all three, only one will have it)
    await redis.lrem("ugc:queue", 1, raw)
    await redis.lrem("ugc:queue:paid", 1, raw)
    await redis.lrem("ugc:queue:parser", 1, raw)
    from fastapi.responses import JSONResponse
    return JSONResponse({"success": True, "message": "Событие успешно опубликовано", "event_id": str(ev.id)})


@app.post("/ugc/reject")
async def ugc_reject(request: Request, raw: str = Form(...), csrf: str = Form(...), redis: aioredis.Redis = Depends(get_redis)) -> Any:
    require_login(request)
    check_csrf(request, csrf)
    # Remove from all queues (try all three, only one will have it)
    await redis.lrem("ugc:queue", 1, raw)
    await redis.lrem("ugc:queue:paid", 1, raw)
    await redis.lrem("ugc:queue:parser", 1, raw)
    from fastapi.responses import JSONResponse
    return JSONResponse({"success": True, "message": "Событие отклонено"})


@app.post("/ugc/bulk-delete")
async def ugc_bulk_delete(request: Request, redis: aioredis.Redis = Depends(get_redis)) -> Any:
    """Bulk delete selected UGC items from queue."""
    require_login(request)

    from fastapi.responses import JSONResponse

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "Invalid JSON"}, status_code=400)

    csrf = body.get("csrf")
    if not csrf:
        return JSONResponse({"success": False, "error": "Missing CSRF token"}, status_code=400)

    check_csrf(request, csrf)

    items = body.get("items", [])
    if not isinstance(items, list):
        return JSONResponse({"success": False, "error": "Items must be an array"}, status_code=400)

    deleted_count = 0
    for item in items:
        if isinstance(item, dict):
            # Reconstruct raw JSON string
            raw = json.dumps(item, ensure_ascii=False)
            # Remove from all queues
            removed = await redis.lrem("ugc:queue", 1, raw)
            if removed == 0:
                removed = await redis.lrem("ugc:queue:paid", 1, raw)
            if removed == 0:
                removed = await redis.lrem("ugc:queue:parser", 1, raw)

            if removed > 0:
                deleted_count += 1

    logger.info("ugc.bulk_delete", deleted_count=deleted_count, total_items=len(items))
    return JSONResponse({"success": True, "deleted_count": deleted_count})


@app.post("/ugc/bulk-ai-process")
async def ugc_bulk_ai_process(
    request: Request,
    session: AsyncSession = Depends(get_session),
    redis: aioredis.Redis = Depends(get_redis)
) -> Any:
    """Bulk process UGC items with AI to validate and format events."""
    require_login(request)

    from fastapi.responses import JSONResponse
    from app.core.llm.is_event_classifier import classify, get_active_classifier_prompt
    from app.core.llm.extractor import extract_event_fields, get_active_extractor_prompt
    from app.db.models import LLMPrompt

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "Invalid JSON"}, status_code=400)

    csrf = body.get("csrf")
    if not csrf:
        return JSONResponse({"success": False, "error": "Missing CSRF token"}, status_code=400)

    check_csrf(request, csrf)

    items = body.get("items", [])
    if not isinstance(items, list):
        return JSONResponse({"success": False, "error": "Items must be an array"}, status_code=400)

    # Load active prompts from database
    classifier_prompt = await get_active_classifier_prompt()
    extractor_prompt = await get_active_extractor_prompt()

    processed = 0
    rejected = 0
    updated = 0

    for item in items:
        if not isinstance(item, dict):
            continue

        raw_text = item.get("raw_text", "")
        if not raw_text or len(raw_text) < 20:
            rejected += 1
            # Remove from queue
            raw_json = json.dumps(item, ensure_ascii=False)
            await redis.lrem("ugc:queue", 1, raw_json)
            await redis.lrem("ugc:queue:paid", 1, raw_json)
            await redis.lrem("ugc:queue:parser", 1, raw_json)
            continue

        try:
            # Step 1: Classify if it's an event using active prompt from DB
            classification = classify(raw_text, custom_prompt=classifier_prompt)

            if not classification.is_event:
                # Not an event - reject it
                rejected += 1
                logger.info("ugc.ai_process.not_event",
                           raw_text_preview=raw_text[:100],
                           reasons=classification.reasons)

                # Remove from queue
                raw_json = json.dumps(item, ensure_ascii=False)
                await redis.lrem("ugc:queue", 1, raw_json)
                await redis.lrem("ugc:queue:paid", 1, raw_json)
                await redis.lrem("ugc:queue:parser", 1, raw_json)
                continue

            # Step 2: Extract event fields using active prompt from DB
            source_url = item.get("source_url")
            draft = extract_event_fields(raw_text, source_url, custom_prompt=extractor_prompt)

            # Step 3: Update the item in queue with extracted data
            updated_item = item.copy()
            updated_item["form"] = {
                "title": draft.title,
                "date_iso": draft.date_iso,
                "time_24h": draft.time_24h,
                "venue_name": draft.venue_name,
                "address": draft.address,
                "price_min": draft.price_min,
                "price_max": draft.price_max,
                "category": draft.category,
                "source_url": draft.source_url or source_url,
            }

            # Replace in Redis: remove old, add new at the end
            old_raw = json.dumps(item, ensure_ascii=False)
            new_raw = json.dumps(updated_item, ensure_ascii=False)

            # Determine which queue to update
            removed = await redis.lrem("ugc:queue", 1, old_raw)
            if removed > 0:
                await redis.rpush("ugc:queue", new_raw)
            else:
                removed = await redis.lrem("ugc:queue:paid", 1, old_raw)
                if removed > 0:
                    await redis.rpush("ugc:queue:paid", new_raw)
                else:
                    removed = await redis.lrem("ugc:queue:parser", 1, old_raw)
                    if removed > 0:
                        await redis.rpush("ugc:queue:parser", new_raw)

            if removed > 0:
                updated += 1
                logger.info("ugc.ai_process.updated",
                           title=draft.title,
                           category=draft.category)

            processed += 1

        except Exception as e:
            logger.error("ugc.ai_process.error",
                        error=str(e),
                        raw_text_preview=raw_text[:100])
            continue

    logger.info("ugc.ai_process.completed",
               processed=processed,
               rejected=rejected,
               updated=updated,
               total_items=len(items))

    return JSONResponse({
        "success": True,
        "processed": processed,
        "rejected": rejected,
        "updated": updated,
    })


# -------- Ads CRUD --------


# -------- Advertisers --------


@app.get("/advertisers", response_class=HTMLResponse)
async def advertisers_list(request: Request, session: AsyncSession = Depends(get_session)) -> Any:
    require_login(request)
    csrf = ensure_csrf(request)
    advertisers = (await session.execute(select(Advertiser).order_by(Advertiser.name))).scalars().all()
    return templates.TemplateResponse("advertisers_list.html", {"request": request, "items": advertisers, "csrf": csrf})


@app.get("/advertisers/new", response_class=HTMLResponse)
async def advertisers_new_form(request: Request) -> Any:
    require_login(request)
    csrf = ensure_csrf(request)
    return templates.TemplateResponse("advertisers_edit.html", {"request": request, "csrf": csrf, "item": None})


@app.get("/advertisers/{advertiser_id}", response_class=HTMLResponse)
async def advertisers_edit_form(advertiser_id: str, request: Request, session: AsyncSession = Depends(get_session)) -> Any:
    require_login(request)
    csrf = ensure_csrf(request)
    item = await session.get(Advertiser, uuid.UUID(advertiser_id))
    if not item:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("advertisers_edit.html", {"request": request, "csrf": csrf, "item": item})


@app.post("/advertisers/save")
async def advertisers_save(
    request: Request,
    csrf: str = Form(...),
    id: Optional[str] = Form(None),
    name: str = Form(...),
    contact_person: Optional[str] = Form(None),
    email: str = Form(...),
    phone: Optional[str] = Form(None),
    balance: float = Form(0),
    session: AsyncSession = Depends(get_session),
) -> Any:
    require_login(request)
    check_csrf(request, csrf)

    # Convert rubles to kopecks
    balance_kopecks = int(balance * 100)

    if id:
        advertiser = await session.get(Advertiser, uuid.UUID(id))
        if not advertiser:
            raise HTTPException(status_code=404)
        advertiser.name = name
        advertiser.contact_person = contact_person
        advertiser.email = email
        advertiser.phone = phone
        advertiser.balance = balance_kopecks
    else:
        advertiser = Advertiser(
            id=uuid.uuid4(),
            name=name,
            contact_person=contact_person,
            email=email,
            phone=phone,
            balance=balance_kopecks,
        )
        session.add(advertiser)

    await session.commit()
    return RedirectResponse("/advertisers", status_code=302)


@app.post("/advertisers/{advertiser_id}/delete")
async def advertisers_delete(
    advertiser_id: str,
    request: Request,
    csrf: str = Form(...),
    session: AsyncSession = Depends(get_session)
) -> Any:
    require_login(request)
    check_csrf(request, csrf)
    advertiser = await session.get(Advertiser, uuid.UUID(advertiser_id))
    if advertiser:
        await session.delete(advertiser)
        await session.commit()
        from fastapi.responses import JSONResponse
        return JSONResponse({"success": True, "message": "Рекламодатель успешно удалён"})
    from fastapi.responses import JSONResponse
    return JSONResponse({"success": False, "error": "Рекламодатель не найден"}, status_code=404)


# -------- Placement Requests --------


@app.get("/placements", response_class=HTMLResponse)
async def placements_list(request: Request, session: AsyncSession = Depends(get_session)) -> Any:
    require_login(request)
    csrf = ensure_csrf(request)
    stmt = (
        select(PlacementRequest)
        .order_by(PlacementRequest.created_at.desc())
    )
    placements = (await session.execute(stmt)).scalars().all()
    return templates.TemplateResponse("placements_list.html", {"request": request, "items": placements, "csrf": csrf})


@app.get("/placements/{placement_id}", response_class=HTMLResponse)
async def placements_view(placement_id: str, request: Request, session: AsyncSession = Depends(get_session)) -> Any:
    require_login(request)
    csrf = ensure_csrf(request)
    item = await session.get(PlacementRequest, uuid.UUID(placement_id))
    if not item:
        raise HTTPException(status_code=404)

    # Load related advertiser
    advertiser = await session.get(Advertiser, item.advertiser_id) if item.advertiser_id else None

    return templates.TemplateResponse(
        "placements_view.html",
        {"request": request, "csrf": csrf, "item": item, "advertiser": advertiser}
    )


@app.post("/placements/{placement_id}/approve")
async def placements_approve(
    placement_id: str,
    request: Request,
    csrf: str = Form(...),
    session: AsyncSession = Depends(get_session),
) -> Any:
    require_login(request)
    check_csrf(request, csrf)

    placement = await session.get(PlacementRequest, uuid.UUID(placement_id))
    if not placement:
        from fastapi.responses import JSONResponse
        return JSONResponse({"success": False, "error": "Размещение не найдено"}, status_code=404)

    placement.status = "approved"
    await session.commit()

    from fastapi.responses import JSONResponse
    return JSONResponse({"success": True, "message": "Размещение подтверждено"})


@app.post("/placements/{placement_id}/reject")
async def placements_reject(
    placement_id: str,
    request: Request,
    csrf: str = Form(...),
    session: AsyncSession = Depends(get_session),
) -> Any:
    require_login(request)
    check_csrf(request, csrf)

    placement = await session.get(PlacementRequest, uuid.UUID(placement_id))
    if not placement:
        from fastapi.responses import JSONResponse
        return JSONResponse({"success": False, "error": "Размещение не найдено"}, status_code=404)

    placement.status = "rejected"
    await session.commit()

    from fastapi.responses import JSONResponse
    return JSONResponse({"success": True, "message": "Размещение отклонено"})


@app.post("/placements/{placement_id}/mark_paid")
async def placements_mark_paid(
    placement_id: str,
    request: Request,
    csrf: str = Form(...),
    session: AsyncSession = Depends(get_session),
) -> Any:
    require_login(request)
    check_csrf(request, csrf)

    placement = await session.get(PlacementRequest, uuid.UUID(placement_id))
    if not placement:
        from fastapi.responses import JSONResponse
        return JSONResponse({"success": False, "error": "Размещение не найдено"}, status_code=404)
    if placement.status != "approved":
        from fastapi.responses import JSONResponse
        return JSONResponse({"success": False, "error": "Размещение должно быть сначала подтверждено"}, status_code=400)

    placement.status = "paid"
    await session.commit()

    from fastapi.responses import JSONResponse
    return JSONResponse({"success": True, "message": "Размещение помечено как оплаченное"})


@app.post("/placements/{placement_id}/activate")
async def placements_activate(
    placement_id: str,
    request: Request,
    csrf: str = Form(...),
    session: AsyncSession = Depends(get_session),
) -> Any:
    require_login(request)
    check_csrf(request, csrf)

    placement = await session.get(PlacementRequest, uuid.UUID(placement_id))
    if not placement:
        from fastapi.responses import JSONResponse
        return JSONResponse({"success": False, "error": "Размещение не найдено"}, status_code=404)
    if placement.status != "paid":
        from fastapi.responses import JSONResponse
        return JSONResponse({"success": False, "error": "Размещение должно быть сначала оплачено"}, status_code=400)

    # Create the actual Event from placement data
    event = Event(
        id=uuid.uuid4(),
        title=placement.event_title or "Платное размещение",
        date=placement.event_date,
        time=placement.event_time,
        category="other",  # PlacementRequest doesn't have event_category field
        venue_name=placement.event_venue or "",  # PlacementRequest uses event_venue, not venue_name
        address=placement.event_address or "",  # Event model uses address, not venue_address
        description=placement.event_description,
        source="paid_placement",
        source_url="",  # Required field, no source in PlacementRequest
        event_type="paid",
        advertiser_id=placement.advertiser_id,
        pricing_model=placement.pricing_model,
        budget=placement.budget,
        spent_budget=0,
        position=placement.position or "standard",
        views=0,
        clicks=0,
    )
    session.add(event)

    placement.status = "active"
    placement.event_id = event.id

    await session.commit()

    from fastapi.responses import JSONResponse
    return JSONResponse({"success": True, "message": "Размещение активировано", "event_id": str(event.id)})


# -------- Stats --------


@app.get("/stats", response_class=HTMLResponse)
async def stats(request: Request, session: AsyncSession = Depends(get_session)) -> Any:
    require_login(request)
    csrf = ensure_csrf(request)

    # Ad interactions per day (views and clicks)
    day = func.date_trunc("day", AdInteraction.created_at).label("day")
    rows = (
        await session.execute(
            select(day, AdInteraction.interaction_type, func.count().label("cnt"))
            .group_by(day, AdInteraction.interaction_type)
            .order_by(day)
        )
    ).all()
    series: dict[str, list[tuple[str, int]]] = {"view": [], "click": []}
    for d, t, c in rows:
        series[t].append((str(d.date()), int(c)))

    # Top paid events by clicks
    top_paid_events = (
        await session.execute(
            select(Event.id, Event.title, Event.clicks, Event.views, Event.spent_budget, Event.budget)
            .where(Event.event_type == "paid")
            .order_by(Event.clicks.desc())
            .limit(10)
        )
    ).all()

    # Revenue statistics
    total_revenue = (
        await session.execute(
            select(func.coalesce(func.sum(PlacementRequest.budget), 0))
            .where(PlacementRequest.status.in_(["paid", "active", "completed"]))
        )
    ).scalar_one()

    pending_requests = (
        await session.execute(
            select(func.count()).where(PlacementRequest.status == "pending")
        )
    ).scalar_one()

    active_placements = (
        await session.execute(
            select(func.count()).where(Event.event_type == "paid", Event.status == "active")
        )
    ).scalar_one()

    return templates.TemplateResponse(
        "stats.html",
        {
            "request": request,
            "csrf": csrf,
            "series": series,
            "top_paid_events": top_paid_events,
            "total_revenue": total_revenue,
            "pending_requests": pending_requests,
            "active_placements": active_placements,
        },
    )
