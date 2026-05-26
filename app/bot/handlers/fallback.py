from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

from app.bot.context import set_user_city


router = Router()


def _menu_kb() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="🍴 Где поесть"), KeyboardButton(text="🎤 Куда сходить")],
        [KeyboardButton(text="🗳 Опрос"), KeyboardButton(text="➕ Добавить событие")],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


_CITIES = {c.lower(): c for c in [
    "Севастополь", "Симферополь", "Ялта", "Евпатория", "Феодосия", "Керчь", "Алушта", "Судак",
]}


@router.message(Command("menu"))
async def show_menu(message: Message) -> None:
    await message.answer("Выберите действие:", reply_markup=_menu_kb())


@router.message(F.text.func(lambda t: isinstance(t, str) and t.strip().lower() in _CITIES))
async def set_city_anytime(message: Message) -> None:
    city = _CITIES[(message.text or "").strip().lower()]
    if message.from_user:
        await set_user_city(message.from_user.id, city)
    await message.answer(f"Город установлен: {city}", reply_markup=_menu_kb())


@router.message()
async def fallback(message: Message) -> None:
    await message.answer("Не понял запрос. Выберите действие:", reply_markup=_menu_kb())

