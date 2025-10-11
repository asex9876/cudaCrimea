from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove

from app.bot.keyboards.common import cities_kb, main_menu_kb
from app.bot.states import StartStates
from app.bot.context import USER_CITY


router = Router()


@router.message(CommandStart())
async def start_cmd(message: Message, state: FSMContext) -> None:
    # If user already has a city, show main menu
    if message.from_user and message.from_user.id in USER_CITY:
        await message.answer("Выберите действие:", reply_markup=main_menu_kb())
        return
    await state.set_state(StartStates.choosing_city)
    await message.answer(
        "Привет! Я помогу найти, куда пойти в Крыму/Севастополе. Выберите город:",
        reply_markup=cities_kb(),
    )


@router.message(StartStates.choosing_city, F.text)
async def choose_city(message: Message, state: FSMContext) -> None:
    city = (message.text or "").strip()
    if message.from_user:
        USER_CITY[message.from_user.id] = city
    await state.update_data(city=city)
    await state.clear()
    await message.answer(f"Отлично! Город установлен: {city}.", reply_markup=main_menu_kb())
