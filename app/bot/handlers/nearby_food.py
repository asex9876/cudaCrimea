from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.client import api_search
from app.bot.keyboards.common import place_actions_kb_with_back, request_location_kb
from app.bot.states import NearbyFoodStates
from app.bot.utils.render import render_place_card
from app.core.services.geo import yandex_deeplink
from app.bot.context import get_user_city


router = Router()


@router.message(F.text == "🍴 Где поесть")
async def ask_location(message: Message, state: FSMContext) -> None:
    await state.set_state(NearbyFoodStates.waiting_location)
    await message.answer(
        "Пришлите геолокацию — подберу места рядом (радиус 2 км)",
        reply_markup=request_location_kb(),
    )


@router.message(NearbyFoodStates.waiting_location, F.location)
async def on_location(message: Message, state: FSMContext) -> None:
    loc = message.location
    if not loc:
        await message.answer("Не получилось получить геолокацию. Попробуйте ещё раз.")
        return
    lat = loc.latitude
    lon = loc.longitude

    user_city = await get_user_city(message.from_user.id if message.from_user else 0)
    params = {
        "city": user_city,
        "when": "today",
        "lat": lat,
        "lon": lon,
        "categories": ["cafe", "bar", "restaurant", "coffee"],
    }
    try:
        data = await api_search(params)
    except Exception:
        await message.answer("Сервис временно недоступен. Попробуйте позже.")
        return

    places = data.get("places", [])[:5]
    if not places:
        await message.answer("Ничего не нашли рядом. Попробуйте изменить локацию.")
        await state.clear()
        return

    for p in places:
        text = render_place_card(type("P", (), p)())  # quick DTO-like
        deeplink = p.get("deeplink") or (yandex_deeplink(p.get("lat"), p.get("lon"), p.get("name")) if p.get("lat") and p.get("lon") else None)
        phone = None
        for b in p.get("buttons", []):
            if b.get("type") == "call":
                phone = b.get("url", "").replace("tel:", "")
        site = None
        for b in p.get("buttons", []):
            if b.get("type") == "site":
                site = b.get("url")
        kb = place_actions_kb_with_back(str(p.get("id")), deeplink or "", phone, site)
        await message.answer(text, reply_markup=kb)

    await state.clear()
