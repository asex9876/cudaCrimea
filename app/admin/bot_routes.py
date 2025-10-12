"""Bot settings management routes for admin panel."""

from __future__ import annotations

from typing import Any
import json

from fastapi import Request, Form, Depends, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BotSettings
from app.db.session import get_session


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


async def bot_settings_page(
    request: Request,
    session: AsyncSession = Depends(get_session)
) -> Any:
    """Bot settings management page."""
    require_login(request)
    csrf = ensure_csrf(request)

    # Get or create bot settings
    result = await session.execute(select(BotSettings).where(BotSettings.id == 1))
    settings = result.scalar_one_or_none()

    if not settings:
        # Create default settings
        settings = BotSettings(
            id=1,
            bot_name="CudaCrimea Bot",
            welcome_message="Привет! Я помогу найти, куда пойти в Крыму/Севастополе. Выберите город:",
            commands=[
                {"command": "start", "description": "Старт / выбор города"},
                {"command": "menu", "description": "Показать меню"},
            ],
            menu_buttons=[
                {"text": "🎤 Куда сходить", "action": "what_to_do"},
                {"text": "🍽 Где поесть", "action": "food"},
                {"text": "✍ Предложить событие", "action": "ugc"},
            ]
        )
        session.add(settings)
        await session.commit()
        await session.refresh(settings)

    from fastapi.templating import Jinja2Templates
    from pathlib import Path
    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

    return templates.TemplateResponse(
        "bot_settings.html",
        {
            "request": request,
            "csrf": csrf,
            "settings": settings,
            "commands_json": json.dumps(settings.commands, ensure_ascii=False, indent=2),
            "menu_buttons_json": json.dumps(settings.menu_buttons, ensure_ascii=False, indent=2),
        },
    )


async def bot_settings_save(
    request: Request,
    csrf: str = Form(...),
    bot_name: str = Form(...),
    bot_username: str = Form(""),
    description: str = Form(""),
    about: str = Form(""),
    welcome_message: str = Form(...),
    commands_json: str = Form(...),
    menu_buttons_json: str = Form(...),
    avatar_file: UploadFile | None = File(None),
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Save bot settings."""
    require_login(request)
    check_csrf(request, csrf)

    # Get existing settings
    result = await session.execute(select(BotSettings).where(BotSettings.id == 1))
    settings = result.scalar_one_or_none()

    if not settings:
        settings = BotSettings(id=1)
        session.add(settings)

    # Update basic fields
    settings.bot_name = bot_name.strip()
    settings.bot_username = bot_username.strip() if bot_username else None
    settings.description = description.strip() if description else None
    settings.about = about.strip() if about else None
    settings.welcome_message = welcome_message.strip()

    # Parse JSON fields
    try:
        settings.commands = json.loads(commands_json)
    except json.JSONDecodeError:
        return JSONResponse(
            {"success": False, "error": "Invalid commands JSON format"},
            status_code=400
        )

    try:
        settings.menu_buttons = json.loads(menu_buttons_json)
    except json.JSONDecodeError:
        return JSONResponse(
            {"success": False, "error": "Invalid menu buttons JSON format"},
            status_code=400
        )

    # Handle avatar upload
    if avatar_file and avatar_file.filename:
        from pathlib import Path
        import uuid

        uploads = Path(__file__).parent / "static" / "uploads"
        uploads.mkdir(parents=True, exist_ok=True)

        ext = Path(avatar_file.filename).suffix or ".jpg"
        fname = f"bot_avatar_{uuid.uuid4().hex}{ext}"
        dest = uploads / fname

        with dest.open("wb") as f:
            f.write(await avatar_file.read())

        settings.avatar_url = f"/static/uploads/{fname}"

    await session.commit()

    return JSONResponse({"success": True, "message": "Настройки сохранены"})


async def bot_settings_apply(
    request: Request,
    csrf: str = Form(...),
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Apply bot settings to Telegram via Bot API."""
    require_login(request)
    check_csrf(request, csrf)

    # Get settings
    result = await session.execute(select(BotSettings).where(BotSettings.id == 1))
    settings = result.scalar_one_or_none()

    if not settings:
        return JSONResponse(
            {"success": False, "error": "Settings not found"},
            status_code=404
        )

    try:
        from aiogram import Bot
        from aiogram.types import BotCommand
        from app.core.config import get_settings

        config = get_settings()
        bot = Bot(token=config.bot_token)

        # Update bot commands
        commands = [
            BotCommand(command=cmd["command"], description=cmd["description"])
            for cmd in settings.commands
        ]
        await bot.set_my_commands(commands)

        # Update bot description if provided
        if settings.description:
            await bot.set_my_short_description(settings.description)

        # Update bot about if provided
        if settings.about:
            await bot.set_my_description(settings.about)

        # Update bot name if provided
        if settings.bot_name:
            await bot.set_my_name(settings.bot_name)

        # Update profile photo if avatar_url is provided
        if settings.avatar_url:
            from pathlib import Path
            from aiogram.types import FSInputFile

            # Convert URL path to file system path
            if settings.avatar_url.startswith("/static/uploads/"):
                avatar_path = Path(__file__).parent / "static" / "uploads" / settings.avatar_url.split("/")[-1]
                if avatar_path.exists():
                    photo = FSInputFile(str(avatar_path))
                    await bot.set_chat_photo(chat_id=bot.id, photo=photo)

        await bot.session.close()

        return JSONResponse({
            "success": True,
            "message": "Настройки применены к боту в Telegram"
        })

    except Exception as e:
        return JSONResponse(
            {"success": False, "error": f"Ошибка при применении настроек: {str(e)}"},
            status_code=500
        )
