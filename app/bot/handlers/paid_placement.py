"""Handlers for paid placement flow with price calculation."""

from __future__ import annotations

from datetime import datetime
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
import httpx
import structlog

from app.bot.states import PaidPlacementStates
from app.core.config import get_settings


logger = structlog.get_logger(module="bot.paid_placement")
router = Router()
settings = get_settings()


def placement_type_kb() -> InlineKeyboardMarkup:
    """Keyboard for selecting placement type."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌍 Весь Крым", callback_data="placement:broadcast_all")],
        [InlineKeyboardButton(text="🏙 Мой город", callback_data="placement:broadcast_city")],
        [InlineKeyboardButton(text="📍 Мой район", callback_data="placement:broadcast_zone")],
        [InlineKeyboardButton(text="🔥 Горящее (срочное)", callback_data="placement:hot")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="placement:cancel")],
    ])


def confirm_placement_kb() -> InlineKeyboardMarkup:
    """Keyboard for confirming placement purchase."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить и оплатить", callback_data="placement:confirm")],
        [InlineKeyboardButton(text="✖️ Отмена", callback_data="placement:cancel")],
    ])


def kb_back_cancel() -> InlineKeyboardMarkup:
    """Simple back/cancel keyboard."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="placement:back")],
        [InlineKeyboardButton(text="✖️ Отмена", callback_data="placement:cancel")],
    ])


async def calculate_price(
    placement_type: str,
    event_date: str,
    event_time: str | None,
    target_city: str | None = None,
    target_zone: str | None = None,
) -> dict | None:
    """Call API to calculate placement price."""
    try:
        # Parse datetime
        from datetime import date as _date, time as _time
        event_dt = _date.fromisoformat(event_date)

        if event_time:
            try:
                hour, minute = map(int, event_time.split(":"))
                time_obj = _time(hour, minute)
                event_datetime = datetime.combine(event_dt, time_obj)
            except:
                event_datetime = datetime.combine(event_dt, _time(12, 0))
        else:
            event_datetime = datetime.combine(event_dt, _time(12, 0))

        payload = {
            "placement_type": placement_type,
            "event_datetime": event_datetime.isoformat(),
            "target_city": target_city,
            "target_zone": target_zone,
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{settings.api_base_url}/api/monetization/calculate-price",
                json=payload,
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error("calculate_price_error", error=str(e))
        return None


async def create_placement(
    user_id: int,
    event_data: dict,
    placement_type: str,
    target_city: str | None = None,
    target_zone: str | None = None,
) -> dict | None:
    """Call API to create paid placement."""
    try:
        payload = {
            "user_id": user_id,
            "event_title": event_data.get("title", ""),
            "event_date": event_data.get("date_iso"),
            "event_time": event_data.get("time_24h"),
            "event_description": None,
            "event_venue": event_data.get("address"),
            "event_address": event_data.get("address"),
            "placement_type": placement_type,
            "target_city": target_city,
            "target_zone": target_zone,
            "contact_name": None,
            "contact_phone": None,
            "contact_email": None,
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{settings.api_base_url}/api/monetization/create-placement",
                json=payload,
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error("create_placement_error", error=str(e), exc_info=True)
        return None


@router.callback_query(F.data.startswith("placement:broadcast_"))
@router.callback_query(F.data == "placement:hot")
async def choose_placement_type(cb: CallbackQuery, state: FSMContext) -> None:
    """User selected placement type - calculate and show price."""
    if not cb.data or not cb.message:
        await cb.answer()
        return

    placement_type = cb.data.replace("placement:", "")
    data = await state.get_data()

    # Get user's city from state or default
    user_city = data.get("city", "Симферополь")
    user_zone = data.get("zone")  # If available

    # Determine targeting based on placement type
    target_city = None
    target_zone = None

    if placement_type == "broadcast_city":
        target_city = user_city
    elif placement_type == "broadcast_zone":
        target_city = user_city
        # For now, ask user to specify zone
        if not user_zone:
            await cb.message.edit_text(
                "📍 Для продвижения по району укажите ваш район в городе:",
                reply_markup=kb_back_cancel()
            )
            await state.set_state(PaidPlacementStates.entering_zone)
            await state.update_data(placement_type=placement_type, target_city=target_city)
            await cb.answer()
            return
        target_zone = user_zone

    # Calculate price
    price_data = await calculate_price(
        placement_type=placement_type,
        event_date=data.get("date_iso", ""),
        event_time=data.get("time_24h"),
        target_city=target_city,
        target_zone=target_zone,
    )

    if not price_data:
        await cb.message.edit_text(
            "❌ Ошибка при расчете цены. Попробуйте позже.",
            reply_markup=placement_type_kb()
        )
        await cb.answer()
        return

    # Store placement details
    await state.update_data(
        placement_type=placement_type,
        target_city=target_city,
        target_zone=target_zone,
        price_data=price_data,
    )

    # Format placement type name
    type_names = {
        "broadcast_all": "🌍 Весь Крым",
        "broadcast_city": f"🏙 Город: {target_city}",
        "broadcast_zone": f"📍 Район: {target_zone} ({target_city})",
        "hot": "🔥 Горящее размещение",
    }

    # Show price and confirmation
    msg = f"""
💰 **Расчет стоимости размещения**

📊 **Тип продвижения:** {type_names.get(placement_type, placement_type)}
👥 **Охват аудитории:** {price_data['audience_size']} человек
📈 **Конверсия:** {price_data['conversion_rate']}%
⏱ **Коэффициент срочности:** {price_data['time_coefficient']}

💵 **ИТОГО:** {price_data['price']:.2f} ₽

{price_data['breakdown']}

Подтвердите создание размещения. После подтверждения вы получите инструкции по оплате.
"""

    await cb.message.edit_text(msg, reply_markup=confirm_placement_kb(), parse_mode="Markdown")
    await state.set_state(PaidPlacementStates.confirming)
    await cb.answer()


@router.message(PaidPlacementStates.entering_zone, F.text)
async def enter_zone(message: Message, state: FSMContext) -> None:
    """User entered zone/district name."""
    zone = (message.text or "").strip()
    data = await state.get_data()

    placement_type = data.get("placement_type")
    target_city = data.get("target_city")

    # Calculate price with zone
    price_data = await calculate_price(
        placement_type=placement_type,
        event_date=data.get("date_iso", ""),
        event_time=data.get("time_24h"),
        target_city=target_city,
        target_zone=zone,
    )

    if not price_data:
        await message.answer(
            "❌ Ошибка при расчете цены. Попробуйте позже.",
            reply_markup=placement_type_kb()
        )
        return

    # Store data
    await state.update_data(
        target_zone=zone,
        price_data=price_data,
    )

    # Show price and confirmation
    msg = f"""
💰 **Расчет стоимости размещения**

📊 **Тип продвижения:** 📍 Район: {zone} ({target_city})
👥 **Охват аудитории:** {price_data['audience_size']} человек
📈 **Конверсия:** {price_data['conversion_rate']}%
⏱ **Коэффициент срочности:** {price_data['time_coefficient']}

💵 **ИТОГО:** {price_data['price']:.2f} ₽

{price_data['breakdown']}

Подтвердите создание размещения. После подтверждения вы получите инструкции по оплате.
"""

    await message.answer(msg, reply_markup=confirm_placement_kb(), parse_mode="Markdown")
    await state.set_state(PaidPlacementStates.confirming)


@router.callback_query(PaidPlacementStates.confirming, F.data == "placement:confirm")
async def confirm_placement(cb: CallbackQuery, state: FSMContext) -> None:
    """User confirmed - create placement request."""
    if not cb.from_user or not cb.message:
        await cb.answer()
        return

    data = await state.get_data()

    # Create placement via API
    result = await create_placement(
        user_id=cb.from_user.id,
        event_data=data,
        placement_type=data.get("placement_type", ""),
        target_city=data.get("target_city"),
        target_zone=data.get("target_zone"),
    )

    if not result:
        await cb.message.edit_text(
            "❌ Ошибка при создании заявки. Попробуйте позже или обратитесь в поддержку.",
        )
        await state.clear()
        await cb.answer()
        return

    price = result.get("calculated_price", 0)
    placement_id = result.get("placement_id", "")

    msg = f"""
✅ **Заявка на размещение создана!**

🆔 Номер заявки: `{placement_id}`
💵 Сумма к оплате: **{price:.2f} ₽**
👥 Охват: {result.get('audience_size', 0)} человек

📋 **Следующие шаги:**
1. Ожидайте проверки модератором
2. После проверки вам придет ссылка на оплату
3. После оплаты ваше событие будет опубликовано

Статус заявки можно проверить в разделе "Мои размещения" (скоро).

Спасибо за использование нашего сервиса! 🎉
"""

    from app.bot.keyboards.common import main_menu_kb

    await cb.message.edit_text(msg, parse_mode="Markdown")
    await cb.message.answer("Выберите действие:", reply_markup=main_menu_kb())
    await state.clear()
    await cb.answer("✅ Заявка создана!")


@router.callback_query(F.data == "placement:cancel")
async def cancel_placement(cb: CallbackQuery, state: FSMContext) -> None:
    """Cancel placement flow."""
    from app.bot.keyboards.common import main_menu_kb

    await state.clear()
    if cb.message:
        await cb.message.edit_text("❌ Создание размещения отменено.")
        await cb.message.answer("Выберите действие:", reply_markup=main_menu_kb())
    await cb.answer()


@router.callback_query(F.data == "placement:back")
async def back_to_type_selection(cb: CallbackQuery, state: FSMContext) -> None:
    """Go back to placement type selection."""
    if not cb.message:
        await cb.answer()
        return

    msg = """
Выберите тип продвижения для вашего события:

🌍 **Весь Крым** - охват всех пользователей
🏙 **Мой город** - только пользователи вашего города
📍 **Мой район** - пользователи вашего района
🔥 **Горящее** - срочная публикация (фиксированная цена)
"""

    await cb.message.edit_text(msg, reply_markup=placement_type_kb())
    await state.set_state(PaidPlacementStates.choosing_type)
    await cb.answer()
