"""Handler for finding events near user's location."""

from __future__ import annotations

import httpx
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from types import SimpleNamespace

from app.bot.keyboards.common import event_actions_kb_with_back
from app.bot.utils.render import render_event_card
from app.core.config import get_settings

router = Router()


@router.message(F.text.in_(["📍 События рядом", "🗺 Рядом со мной"]))
async def ask_location_for_nearby(message: Message, state: FSMContext) -> None:
    """Ask user to share location to find nearby events."""
    from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📍 Отправить местоположение", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await message.answer(
        "📍 **События рядом с вами**\n\n"
        "Отправьте вашу геолокацию, чтобы я показал события в радиусе 5 км от вас.",
        reply_markup=kb,
    )
    await state.set_state("waiting_location_for_nearby")


@router.message(F.location)
async def show_nearby_events(message: Message, state: FSMContext) -> None:
    """Show events near user's location."""
    loc = message.location
    if not loc:
        await message.answer("❌ Не удалось получить геолокацию")
        return

    # Clear state
    await state.clear()

    # Show loading message
    loading_msg = await message.answer("🔍 Ищу события рядом с вами...")

    settings = get_settings()
    api_url = f"{settings.api_base_url}/api/events/nearby"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                api_url,
                params={
                    "lat": loc.latitude,
                    "lon": loc.longitude,
                    "radius": 5.0,
                    "limit": 10,
                },
            )
            response.raise_for_status()
            data = response.json()

        events = data.get("events", [])

        if not events:
            await loading_msg.edit_text(
                "😔 **Событий поблизости не найдено**\n\n"
                "Попробуйте увеличить радиус поиска или посмотрите события в вашем городе."
            )
            return

        # Save events to state for navigation
        await state.update_data(nearby_events=events, nearby_index=0)

        # Show first event
        await show_nearby_event(loading_msg, state, 0)

    except Exception as e:
        import structlog

        logger = structlog.get_logger()
        logger.error("nearby_events.error", error=str(e), lat=loc.latitude, lon=loc.longitude)
        await loading_msg.edit_text(
            "❌ **Ошибка при поиске событий**\n\n" "Попробуйте позже или обратитесь в поддержку."
        )


async def show_nearby_event(message: Message, state: FSMContext, index: int) -> None:
    """Show a specific event from nearby results."""
    data = await state.get_data()
    events = data.get("nearby_events", [])

    if not events or index < 0 or index >= len(events):
        await message.edit_text("❌ Событие не найдено")
        return

    event = events[index]
    total = len(events)

    # Build event card
    event_obj = SimpleNamespace(
        title=event["title"],
        date=event["date"],
        time=event.get("time"),
        venue_name=event["venue_name"],
        address=event["address"],
        price_min=event.get("price_min"),
        price_max=event.get("price_max"),
        category=event["category"],
    )

    card = render_event_card(event_obj)
    distance = event["distance_km"]
    district = event.get("district")

    # Build text
    parts = [
        f"📍 **Событие {index + 1} из {total}**",
        f"📏 Расстояние: **{distance} км**",
    ]

    if district:
        parts.append(f"🏘 Район: {district}")

    parts.append("")  # Empty line
    parts.append(card)

    if event.get("deeplink"):
        parts.append(f"\n📍 Маршрут: {event['deeplink']}")

    text = "\n".join(parts)

    # Build keyboard
    kb_rows = []

    # Action buttons
    action_row = []
    if event.get("deeplink"):
        action_row.append(InlineKeyboardButton(text="🗺 Маршрут", url=event["deeplink"]))
    if event.get("source_url"):
        action_row.append(InlineKeyboardButton(text="🌐 Сайт", url=event["source_url"]))
    if action_row:
        kb_rows.append(action_row)

    # Navigation
    if total > 1:
        nav_row = [
            InlineKeyboardButton(text="◀️", callback_data="nearby:prev"),
            InlineKeyboardButton(text=f"{index + 1}/{total}", callback_data="nearby:noop"),
            InlineKeyboardButton(text="▶️", callback_data="nearby:next"),
        ]
        kb_rows.append(nav_row)

    # Back to menu
    from app.bot.keyboards.common import main_menu_kb

    kb_rows.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="nav:back")])

    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    await state.update_data(nearby_index=index)
    await message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data == "nearby:next")
async def nearby_next(cb: CallbackQuery, state: FSMContext) -> None:
    """Show next nearby event."""
    if not cb.message:
        await cb.answer()
        return

    data = await state.get_data()
    events = data.get("nearby_events", [])
    current = data.get("nearby_index", 0)

    if not events:
        await cb.answer("❌ Нет событий")
        return

    next_index = (current + 1) % len(events)
    await show_nearby_event(cb.message, state, next_index)
    await cb.answer()


@router.callback_query(F.data == "nearby:prev")
async def nearby_prev(cb: CallbackQuery, state: FSMContext) -> None:
    """Show previous nearby event."""
    if not cb.message:
        await cb.answer()
        return

    data = await state.get_data()
    events = data.get("nearby_events", [])
    current = data.get("nearby_index", 0)

    if not events:
        await cb.answer("❌ Нет событий")
        return

    prev_index = (current - 1) % len(events)
    await show_nearby_event(cb.message, state, prev_index)
    await cb.answer()


@router.callback_query(F.data == "nearby:noop")
async def nearby_noop(cb: CallbackQuery) -> None:
    """No-op callback for counter button."""
    await cb.answer()
