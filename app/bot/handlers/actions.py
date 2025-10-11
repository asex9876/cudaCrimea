from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.core.services.geo import yandex_deeplink
# from app.db.dao.clicks import log_click  # TODO: Migrate to AdInteraction
from app.db.session import get_sessionmaker


router = Router()


@router.callback_query(F.data.startswith("act:"))
async def on_action(cb: CallbackQuery) -> None:
    user_id = cb.from_user.id if cb.from_user else 0
    parts = (cb.data or "").split(":")
    # act:<action>:<type>:<id>
    if len(parts) != 4:
        await cb.answer("Некорректная команда", show_alert=True)
        return
    _, action, item_type, item_id = parts

    # TODO: Migrate to AdInteraction tracking
    # Log click
    # ss = get_sessionmaker()
    # async with ss() as session:  # type: ignore[call-arg]
    #     await log_click(session, user_tg=user_id, item_type=item_type, item_id=item_id, action=action)

    # Reply with URL (best-effort), actual deeplink must be generated client-side; here we provide a generic opener
    if action == "route":
        await cb.answer("Ссылка отправлена")
        await cb.message.answer("Откройте маршрут в Яндекс.Картах. Уточните адрес в карточке.")
    elif action == "call":
        await cb.answer("Номер отправлен")
        await cb.message.answer("Нажмите на номер в карточке, чтобы позвонить.")
    elif action in {"site", "book"}:
        await cb.answer("Ссылка отправлена")
        await cb.message.answer("Перейдите по ссылке из карточки.")
    else:
        await cb.answer("Готово")

