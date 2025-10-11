from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.bot.keyboards.common import main_menu_kb


router = Router()


@router.callback_query(F.data == "nav:back")
async def on_nav_back(cb: CallbackQuery) -> None:
    await cb.answer()
    await cb.message.answer("Вернулся в меню. Выберите раздел:", reply_markup=main_menu_kb())

