"""Telegram channel management routes."""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from fastapi import Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.db.models import TelegramChannel, TelegramAccount, Event
from app.db.session import get_session
from app.core import runtime_config as rc

logger = structlog.get_logger(module="admin.telegram_channels")


async def telegram_channels_page(request: Request, session: AsyncSession = Depends(get_session)) -> Any:
    """Display Telegram channels management page."""
    from app.admin.main import require_login, ensure_csrf, templates

    require_login(request)
    csrf = ensure_csrf(request)

    # Get all channels with statistics
    channels = (await session.execute(
        select(TelegramChannel).order_by(TelegramChannel.added_at.desc())
    )).scalars().all()

    # Get active Telegram accounts
    tg_accounts = (await session.execute(
        select(TelegramAccount)
        .where(TelegramAccount.status == "active")
        .order_by(TelegramAccount.created_at.desc())
    )).scalars().all()

    # Get selected account ID from config
    selected_tg_account_id = rc.get("tg_account_id")

    return templates.TemplateResponse(
        "telegram_channels.html",
        {
            "request": request,
            "csrf": csrf,
            "channels": channels,
            "tg_accounts": tg_accounts,
            "selected_tg_account_id": selected_tg_account_id,
        }
    )


async def verify_telegram_channel(
    request: Request,
    csrf: str = Form(...),
    url: str = Form(...),
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Verify that a Telegram channel/group/chat exists and is accessible."""
    from app.admin.main import require_login, check_csrf

    require_login(request)
    check_csrf(request, csrf)

    logger.info("telegram_channel.verify.start", url=url)

    try:
        # Clean up URL to extract username
        username = url.strip()

        # Handle different URL formats
        if username.startswith("https://t.me/"):
            username = username.replace("https://t.me/", "")
        elif username.startswith("http://t.me/"):
            username = username.replace("http://t.me/", "")
        elif username.startswith("@"):
            username = username[1:]

        # Remove trailing slashes or query params
        username = username.split("/")[0].split("?")[0].strip()

        if not username:
            return JSONResponse({
                "success": False,
                "error": "Неверный формат ссылки",
                "username": username
            })

        # Get active Telegram account
        tg_account_id = rc.get("tg_account_id")
        if not tg_account_id:
            return JSONResponse({
                "success": False,
                "error": "Telegram аккаунт не настроен. Добавьте аккаунт в разделе 'Телеграм аккаунты'",
                "username": username
            })

        tg_account = await session.get(TelegramAccount, uuid.UUID(tg_account_id))
        if not tg_account or tg_account.status != "active":
            return JSONResponse({
                "success": False,
                "error": "Telegram аккаунт не активен",
                "username": username
            })

        # Connect to Telegram
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        from telethon.errors import UsernameInvalidError, UsernameNotOccupiedError

        client = TelegramClient(
            StringSession(tg_account.session_string),
            tg_account.api_id,
            tg_account.api_hash
        )
        await client.connect()

        try:
            # Try to get entity (channel/group/chat)
            entity = await client.get_entity(username)

            # Get channel info
            channel_info = {
                "success": True,
                "username": username,
                "title": getattr(entity, "title", username),
                "channel_id": entity.id,
                "url": f"https://t.me/{username}",
                "verified": True,
            }

            logger.info("telegram_channel.verify.success", username=username, title=channel_info["title"])
            return JSONResponse(channel_info)

        except (UsernameInvalidError, UsernameNotOccupiedError) as e:
            logger.warning("telegram_channel.verify.not_found", username=username, error=str(e))
            return JSONResponse({
                "success": False,
                "error": "Канал не найден или недоступен",
                "username": username,
                "verified": False
            })
        finally:
            await client.disconnect()

    except Exception as e:
        logger.error("telegram_channel.verify.error", error=str(e), error_type=type(e).__name__)
        return JSONResponse({
            "success": False,
            "error": f"Ошибка проверки: {str(e)[:100]}",
            "username": username if 'username' in locals() else url
        })


async def add_telegram_channel(
    request: Request,
    csrf: str = Form(...),
    username: str = Form(...),
    title: str = Form(...),
    channel_id: int = Form(...),
    url: str = Form(...),
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Add a verified Telegram channel to the database."""
    from app.admin.main import require_login, check_csrf

    require_login(request)
    check_csrf(request, csrf)

    logger.info("telegram_channel.add", username=username, title=title)

    try:
        # Check if channel already exists
        existing = (await session.execute(
            select(TelegramChannel).where(TelegramChannel.username == username)
        )).scalar_one_or_none()

        if existing:
            return JSONResponse({
                "success": False,
                "error": "Этот канал уже добавлен"
            })

        # Create new channel
        channel = TelegramChannel(
            id=uuid.uuid4(),
            username=username,
            title=title,
            channel_id=channel_id,
            url=url,
            status="active",
            is_verified=True,
            last_check_at=datetime.utcnow(),
            added_by="admin",  # Could be request.session.get("username") if you track users
        )
        session.add(channel)
        await session.commit()

        logger.info("telegram_channel.add.success", channel_id=str(channel.id), username=username)
        return JSONResponse({
            "success": True,
            "message": "Канал успешно добавлен",
            "channel_id": str(channel.id)
        })

    except Exception as e:
        logger.error("telegram_channel.add.error", error=str(e))
        return JSONResponse({
            "success": False,
            "error": f"Ошибка добавления: {str(e)[:100]}"
        })


async def delete_telegram_channel(
    request: Request,
    csrf: str = Form(...),
    channel_id: str = Form(...),
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Delete a Telegram channel from the database."""
    from app.admin.main import require_login, check_csrf

    require_login(request)
    check_csrf(request, csrf)

    logger.info("telegram_channel.delete", channel_id=channel_id)

    try:
        channel = await session.get(TelegramChannel, uuid.UUID(channel_id))
        if not channel:
            return JSONResponse({
                "success": False,
                "error": "Канал не найден"
            }, status_code=404)

        await session.delete(channel)
        await session.commit()

        logger.info("telegram_channel.delete.success", channel_id=channel_id)
        return JSONResponse({
            "success": True,
            "message": "Канал успешно удалён"
        })

    except Exception as e:
        logger.error("telegram_channel.delete.error", error=str(e))
        return JSONResponse({
            "success": False,
            "error": f"Ошибка удаления: {str(e)[:100]}"
        })


async def list_telegram_channels(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Get list of all channels with statistics (API endpoint for AJAX)."""
    from app.admin.main import require_login

    require_login(request)

    try:
        # Get all channels
        channels = (await session.execute(
            select(TelegramChannel).order_by(TelegramChannel.added_at.desc())
        )).scalars().all()

        # Build response with calculated percentages
        channel_list = []
        for ch in channels:
            # Calculate percentage: parsed / total_messages_seen
            percentage = 0.0
            if ch.total_messages_seen > 0:
                percentage = round((ch.total_parsed / ch.total_messages_seen) * 100, 1)

            channel_list.append({
                "id": str(ch.id),
                "username": ch.username,
                "title": ch.title,
                "url": ch.url,
                "status": ch.status,
                "is_verified": ch.is_verified,
                "added_at": ch.added_at.isoformat() if ch.added_at else None,
                "total_messages_seen": ch.total_messages_seen,
                "total_parsed": ch.total_parsed,
                "total_published": ch.total_published,
                "percentage": percentage,
                "last_error": ch.last_error,
            })

        return JSONResponse({
            "success": True,
            "channels": channel_list
        })

    except Exception as e:
        logger.error("telegram_channel.list.error", error=str(e))
        return JSONResponse({
            "success": False,
            "error": f"Ошибка загрузки: {str(e)[:100]}"
        })
