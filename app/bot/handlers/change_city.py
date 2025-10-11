from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.keyboards.common import cities_kb
from app.bot.states import StartStates


router = Router()


@router.message(F.text == "Сменить город")
async def change_city_btn(message: Message, state: FSMContext) -> None:
    await state.set_state(StartStates.choosing_city)
    await message.answer("Выберите город:", reply_markup=cities_kb())


@router.message(Command("city"))
async def change_city_cmd(message: Message, state: FSMContext) -> None:
    await state.set_state(StartStates.choosing_city)
    await message.answer("Выберите город:", reply_markup=cities_kb())

