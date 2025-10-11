"""Telegram accounts management routes."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import structlog
from fastapi import Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TelegramAccount
from app.db.session import get_session

logger = structlog.get_logger(module="admin.telegram")
STATIC_DIR = Path(__file__).parent / "static"


async def telegram_accounts_list(request: Request, session: AsyncSession = Depends(get_session)) -> Any:
    """Display Telegram accounts management page."""
    from app.admin.main import require_login, ensure_csrf, templates

    require_login(request)
    csrf = ensure_csrf(request)

    # Get all accounts
    accounts = (await session.execute(
        select(TelegramAccount).order_by(TelegramAccount.created_at.desc())
    )).scalars().all()

    # Check if there's a pending account in session
    pending_account = None
    if "pending_tg_account_id" in request.session:
        pending_id = request.session["pending_tg_account_id"]
        pending_account = await session.get(TelegramAccount, uuid.UUID(pending_id))

    # If no pending in session, find latest pending account
    if not pending_account:
        pending_account = (await session.execute(
            select(TelegramAccount)
            .where(TelegramAccount.status == "pending")
            .order_by(TelegramAccount.created_at.desc())
            .limit(1)
        )).scalar_one_or_none()

    return templates.TemplateResponse(
        "telegram_accounts.html",
        {
            "request": request,
            "csrf": csrf,
            "accounts": accounts,
            "pending_account": pending_account,
        }
    )


async def telegram_accounts_add(
    request: Request,
    csrf: str = Form(...),
    phone: str = Form(...),
    api_id: str = Form(...),
    api_hash: str = Form(...),
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Start Telegram account authorization process."""
    from app.admin.main import require_login, check_csrf

    require_login(request)
    check_csrf(request, csrf)

    logger.info("telegram.add.start", phone=phone, api_id=api_id)

    try:
        # Validate API ID
        api_id_int = int(api_id)

        # Check if phone already exists
        existing = (await session.execute(
            select(TelegramAccount).where(TelegramAccount.phone == phone)
        )).scalar_one_or_none()

        if existing:
            return {"success": False, "error": "Этот номер телефона уже добавлен"}

        # Create new account
        account = TelegramAccount(
            id=uuid.uuid4(),
            phone=phone,
            api_id=api_id_int,
            api_hash=api_hash,
            status="pending",
            is_active=False,
        )
        session.add(account)
        await session.commit()

        # Start Telegram auth process
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        client = TelegramClient(StringSession(), api_id_int, api_hash)
        await client.connect()

        # Send code and get hash
        logger.info("telegram.add.sending_code", phone=phone)
        code_result = await client.send_code_request(phone)
        logger.info("telegram.add.code_sent", phone_code_hash=code_result.phone_code_hash[:20])

        # Save session string and phone_code_hash
        account.session_string = client.session.save()
        account.phone_code_hash = code_result.phone_code_hash
        await session.commit()
        logger.info("telegram.add.saved", account_id=str(account.id))

        await client.disconnect()

        # Store account ID in session for code confirmation
        request.session["pending_tg_account_id"] = str(account.id)

        return {"success": True, "account_id": str(account.id), "phone": phone}

    except ValueError as e:
        logger.error("telegram.add.value_error", error=str(e))
        return {"success": False, "error": "Неверный формат API ID"}
    except Exception as e:
        logger.error("telegram.add.error", error=str(e), error_type=type(e).__name__)
        import traceback
        logger.error("telegram.add.traceback", tb=traceback.format_exc())
        error_msg = str(e)
        if "phone" in error_msg.lower():
            error_msg = "Неверный номер телефона"
        elif "api" in error_msg.lower():
            error_msg = "Неверные API credentials"
        return {"success": False, "error": error_msg[:100]}


async def telegram_accounts_confirm(
    request: Request,
    csrf: str = Form(...),
    account_id: str = Form(...),
    code: str = Form(...),
    password: str = Form(""),
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Confirm Telegram authorization with code."""
    from app.admin.main import require_login, check_csrf

    require_login(request)
    check_csrf(request, csrf)

    logger.info("telegram.confirm.start", account_id=account_id, code=code[:2]+"***", has_password=bool(password))

    try:
        account = await session.get(TelegramAccount, uuid.UUID(account_id))
        if not account:
            return {"success": False, "error": "Аккаунт не найден"}

        from telethon import TelegramClient
        from telethon.sessions import StringSession

        # Restore session
        client = TelegramClient(
            StringSession(account.session_string),
            account.api_id,
            account.api_hash
        )
        await client.connect()

        # Sign in with code (step 1)
        needs_password = False
        try:
            await client.sign_in(
                account.phone,
                code,
                phone_code_hash=account.phone_code_hash
            )
        except Exception as e:
            error_str = str(e).lower()
            if "password" in error_str or "2fa" in error_str or "session password needed" in error_str:
                # Need 2FA password - this is expected
                needs_password = True
                logger.info("telegram.confirm.needs_password", account_id=account_id)
            elif "code" in error_str or "invalid" in error_str:
                await client.disconnect()
                return {"success": False, "error": "Неверный код подтверждения"}
            else:
                # Unexpected error
                await client.disconnect()
                logger.error("telegram.confirm.signin_error", error=str(e))
                raise

        # If 2FA password is needed, sign in with password (step 2)
        if needs_password:
            if not password:
                await client.disconnect()
                return {"success": False, "error": "Требуется 2FA пароль", "needs_password": True}

            try:
                await client.sign_in(password=password)
                logger.info("telegram.confirm.password_accepted", account_id=account_id)
            except Exception as e:
                error_str = str(e).lower()
                await client.disconnect()
                if "password" in error_str or "invalid" in error_str:
                    return {"success": False, "error": "Неверный 2FA пароль"}
                else:
                    logger.error("telegram.confirm.password_error", error=str(e))
                    raise

        # Get user info
        me = await client.get_me()
        account.user_id = me.id
        account.first_name = me.first_name
        account.last_name = me.last_name
        account.username = me.username

        # Download profile photo
        try:
            photo = await client.download_profile_photo(me, bytes)
            if photo:
                # Save photo to static/uploads
                uploads = STATIC_DIR / "uploads"
                uploads.mkdir(parents=True, exist_ok=True)
                fname = f"tg_avatar_{account.id}.jpg"
                dest = uploads / fname
                with dest.open("wb") as f:
                    f.write(photo)
                account.photo_url = f"/static/uploads/{fname}"
        except Exception:
            pass  # Photo optional

        # Save final session
        account.session_string = client.session.save()
        account.status = "active"
        account.is_active = True
        await session.commit()

        await client.disconnect()

        # Clear session
        if "pending_tg_account_id" in request.session:
            del request.session["pending_tg_account_id"]

        return {"success": True}

    except Exception as e:
        logger.error("telegram.confirm.error", error=str(e))
        return {"success": False, "error": str(e)[:100]}


async def telegram_accounts_delete(
    request: Request,
    csrf: str = Form(...),
    account_id: str = Form(...),
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Delete Telegram account."""
    from app.admin.main import require_login, check_csrf

    require_login(request)
    check_csrf(request, csrf)

    account = await session.get(TelegramAccount, uuid.UUID(account_id))
    if account:
        await session.delete(account)
        await session.commit()

    return RedirectResponse("/telegram-accounts", status_code=302)
