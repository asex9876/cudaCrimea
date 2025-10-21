from __future__ import annotations

import re
from datetime import date as _date
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from pathlib import Path
import uuid
import httpx
import asyncio

from app.bot.client import api_ugc_submit
from app.bot.keyboards.common import cities_kb, interests_kb, request_location_kb
from app.bot.states import UGCFormStates
from app.core.config import get_settings
from app.core.services.geocoding import GeocodingService
from app.db.session import get_session


router = Router()


def _time_prompt_text(error: str | None = None) -> str:
    base = "Шаг 3/10. Время (ЧЧ:ММ) или 'пропустить':"
    if error:
        return f"{error}\n\n{base}"
    return base


def kb_back(cancel: bool = True, back_cb: str = "form:back", skip_cb: str | None = None) -> InlineKeyboardMarkup:
    """Create keyboard with Back (and optionally Skip and Cancel) buttons."""
    rows = []
    if skip_cb:
        rows.append([InlineKeyboardButton(text="⏭ Пропустить", callback_data=skip_cb)])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=back_cb)])
    if cancel:
        rows.append([InlineKeyboardButton(text="✖️ Отмена", callback_data="form:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _ui_update(bot, state: FSMContext, chat_id: int, text: str, kb=None, force_new: bool = False) -> None:
    """Always send a new message for each step (no editing)."""
    from aiogram.types import ReplyKeyboardMarkup

    # Always send new message on each step
    m = await bot.send_message(chat_id, text, reply_markup=kb)

    # Track if using ReplyKeyboardMarkup
    is_reply_kb = isinstance(kb, ReplyKeyboardMarkup)
    await state.update_data(_ui_msg_id=m.message_id, _ui_chat_id=chat_id, _last_kb_was_reply=is_reply_kb)


@router.message(F.text == "/addevent")
@router.message(F.text == "➕ Добавить событие")
@router.message(F.text.contains("Добавить событие"))
@router.message(F.text == "? �������� ᮡ�⨥")
async def form_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(UGCFormStates.entering_title)
    await state.update_data(_flow_stack=["entering_title"])  # simple manual stack
    await _ui_update(message.bot, state, message.chat.id, "Шаг 1/10. Введите название события:", kb_back(cancel=True))


@router.message(UGCFormStates.entering_title, F.text)
async def form_title(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    await state.update_data(title=title)
    await state.set_state(UGCFormStates.entering_date)
    # push stack
    data = await state.get_data()
    stack = list(data.get("_flow_stack", []))
    stack.append("entering_date")
    await state.update_data(_flow_stack=stack)
    await _ui_update(message.bot, state, message.chat.id, "Шаг 2/10. Дата (ГГГГ-ММ-ДД):", kb_back(skip_cb="form:skip:date"))


@router.callback_query(UGCFormStates.entering_date, F.data == "form:skip:date")
async def skip_date(cb: CallbackQuery, state: FSMContext) -> None:
    """Skip date field."""
    await state.update_data(date_iso=None)
    await state.set_state(UGCFormStates.entering_time)
    data = await state.get_data()
    stack = list(data.get("_flow_stack", []))
    stack.append("entering_time")
    await state.update_data(_flow_stack=stack)
    chat_id = cb.message.chat.id if cb.message and cb.message.chat else 0
    await _ui_update(cb.message.bot, state, chat_id, "Шаг 3/10. Время (ЧЧ:ММ):", kb_back(skip_cb="form:skip:time"))
    await cb.answer("⏭ Дата пропущена")


@router.message(UGCFormStates.entering_date, F.text)
async def form_date(message: Message, state: FSMContext) -> None:
    txt = (message.text or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", txt):
        await message.answer("❌ Неверный формат. Пример: 2025-10-15")
        return
    try:
        event_date = _date.fromisoformat(txt)
    except Exception:
        await message.answer("❌ Такая дата недопустима. Введите снова.")
        return

    # Validate date is not in the past
    from datetime import datetime, timedelta
    today = datetime.now().date()
    max_date = today + timedelta(days=180)  # 6 months ~ 180 days

    if event_date < today:
        await message.answer("❌ Дата не может быть в прошлом. Введите актуальную дату.")
        return

    if event_date > max_date:
        await message.answer(f"❌ Дата не может быть позднее {max_date.strftime('%Y-%m-%d')} (максимум 6 месяцев вперёд).")
        return

    await state.update_data(date_iso=txt)
    await state.set_state(UGCFormStates.entering_time)
    data = await state.get_data()
    stack = list(data.get("_flow_stack", []))
    stack.append("entering_time")
    await state.update_data(_flow_stack=stack)
    await _ui_update(message.bot, state, message.chat.id, "Шаг 3/10. Время (ЧЧ:ММ):", kb_back(skip_cb="form:skip:time"))


@router.callback_query(UGCFormStates.entering_time, F.data == "form:skip:time")
async def skip_time(cb: CallbackQuery, state: FSMContext) -> None:
    """Skip time field."""
    await state.update_data(time_24h=None)
    await state.set_state(UGCFormStates.choosing_city)
    data = await state.get_data()
    stack = list(data.get("_flow_stack", []))
    stack.append("choosing_city")
    await state.update_data(_flow_stack=stack)
    chat_id = cb.message.chat.id if cb.message and cb.message.chat else 0
    await _ui_update(cb.message.bot, state, chat_id, "Шаг 4/10. Выберите город:", cities_kb())
    await cb.answer("⏭ Время пропущено")


@router.message(UGCFormStates.entering_time, F.text)
async def form_time(message: Message, state: FSMContext) -> None:
    chat = message.chat
    if not chat:
        return
    txt = (message.text or "").strip()
    if not re.fullmatch(r"\d{2}:\d{2}", txt):
        await message.answer("❌ Неверный формат. Пример: 19:00")
        return
    hours, minutes = map(int, txt.split(":"))
    if not (0 <= hours < 24 and 0 <= minutes < 60):
        await message.answer("❌ Время должно быть в диапазоне 00:00–23:59")
        return
    await state.update_data(time_24h=txt)
    await state.set_state(UGCFormStates.choosing_city)
    data = await state.get_data()
    stack = list(data.get("_flow_stack", []))
    stack.append("choosing_city")
    await state.update_data(_flow_stack=stack)
    await _ui_update(message.bot, state, chat.id, "Шаг 4/10. Выберите город:", cities_kb())


@router.message(UGCFormStates.choosing_city, F.text)
async def form_city(message: Message, state: FSMContext) -> None:
    city = (message.text or "").strip()
    await state.update_data(city=city)
    await state.set_state(UGCFormStates.entering_address)
    data = await state.get_data()
    stack = list(data.get("_flow_stack", []))
    stack.append("entering_address")
    await state.update_data(_flow_stack=stack)
    await _ui_update(message.bot, state, message.chat.id, "Шаг 5/10. Укажите адрес текстом или отправьте геолокацию кнопкой ниже.", request_location_kb())


@router.message(UGCFormStates.entering_address, F.location)
async def form_location(message: Message, state: FSMContext) -> None:
    loc = message.location
    if loc:
        # Try reverse geocoding to get district
        async for session in get_session():
            try:
                geocoding_service = GeocodingService(session)
                address_info = await geocoding_service.reverse_geocode(
                    loc.latitude, loc.longitude
                )

                if address_info:
                    district = address_info.get("district")
                    road = address_info.get("road")
                    house_number = address_info.get("house_number")

                    # Build address string
                    address_parts = []
                    if road:
                        address_parts.append(road)
                    if house_number:
                        address_parts.append(house_number)
                    address_str = ", ".join(address_parts) if address_parts else None

                    await state.update_data(
                        lat=loc.latitude,
                        lon=loc.longitude,
                        district=district,
                        address=address_str
                    )

                    # Notify user
                    if district:
                        await message.answer(f"✅ Район определен: {district}")
                else:
                    await state.update_data(lat=loc.latitude, lon=loc.longitude)
                    await message.answer("✅ Геолокация сохранена")

            except Exception as e:
                # If reverse geocoding fails, still save coordinates
                await state.update_data(lat=loc.latitude, lon=loc.longitude)
                import structlog
                logger = structlog.get_logger()
                logger.error("ugc_form.reverse_geocoding_error", lat=loc.latitude, lon=loc.longitude, error=str(e))

    await state.set_state(UGCFormStates.entering_price_min)
    data = await state.get_data()
    stack = list(data.get("_flow_stack", []))
    stack.append("entering_price_min")
    await state.update_data(_flow_stack=stack)
    await _ui_update(message.bot, state, message.chat.id, "Шаг 6/10. Минимальная цена (число) или 'пропустить':", kb_back())


@router.message(UGCFormStates.entering_address, F.text)
async def form_address_text(message: Message, state: FSMContext) -> None:
    addr = (message.text or "").strip()
    data = await state.get_data()
    city = data.get("city", "Севастополь")

    # Try to geocode the address
    async for session in get_session():
        try:
            geocoding_service = GeocodingService(session)
            result = await geocoding_service.geocode_address(addr, city)

            if result:
                lat, lon, district = result
                await state.update_data(
                    address=addr,
                    lat=lat,
                    lon=lon,
                    district=district
                )
                # Notify user about successful geocoding
                if district:
                    await message.answer(f"✅ Адрес определен: {district}")
                else:
                    await message.answer(f"✅ Координаты определены")
            else:
                # Geocoding failed, but still save the address
                await state.update_data(address=addr)
                await message.answer("⚠️ Не удалось определить точные координаты, но адрес сохранен")

        except Exception as e:
            # If geocoding fails, still save the address
            await state.update_data(address=addr)
            import structlog
            logger = structlog.get_logger()
            logger.error("ugc_form.geocoding_error", address=addr, error=str(e))

    await state.set_state(UGCFormStates.entering_price_min)
    stack = list(data.get("_flow_stack", []))
    stack.append("entering_price_min")
    await state.update_data(_flow_stack=stack)
    await _ui_update(message.bot, state, message.chat.id, "Шаг 6/10. Минимальная цена (число):", kb_back(skip_cb="form:skip:price_min"))


@router.callback_query(UGCFormStates.entering_price_min, F.data == "form:skip:price_min")
async def skip_price_min(cb: CallbackQuery, state: FSMContext) -> None:
    """Skip price_min field."""
    await state.update_data(price_min=None)
    await state.set_state(UGCFormStates.entering_price_max)
    data = await state.get_data()
    stack = list(data.get("_flow_stack", []))
    stack.append("entering_price_max")
    await state.update_data(_flow_stack=stack)
    chat_id = cb.message.chat.id if cb.message and cb.message.chat else 0
    await _ui_update(cb.message.bot, state, chat_id, "Шаг 7/10. Максимальная цена (число):", kb_back(skip_cb="form:skip:price_max"))
    await cb.answer("⏭ Минимальная цена пропущена")


@router.message(UGCFormStates.entering_price_min, F.text)
async def form_price_min(message: Message, state: FSMContext) -> None:
    txt = (message.text or "").strip()
    if not re.fullmatch(r"\d+", txt):
        await message.answer("❌ Введите число")
        return
    await state.update_data(price_min=int(txt))
    await state.set_state(UGCFormStates.entering_price_max)
    data = await state.get_data()
    stack = list(data.get("_flow_stack", []))
    stack.append("entering_price_max")
    await state.update_data(_flow_stack=stack)
    await _ui_update(message.bot, state, message.chat.id, "Шаг 7/10. Максимальная цена (число):", kb_back(skip_cb="form:skip:price_max"))


@router.callback_query(UGCFormStates.entering_price_max, F.data == "form:skip:price_max")
async def skip_price_max(cb: CallbackQuery, state: FSMContext) -> None:
    """Skip price_max field."""
    await state.update_data(price_max=None)
    await state.set_state(UGCFormStates.choosing_category)
    data = await state.get_data()
    stack = list(data.get("_flow_stack", []))
    stack.append("choosing_category")
    await state.update_data(_flow_stack=stack, selected_categories=[])
    chat_id = cb.message.chat.id if cb.message and cb.message.chat else 0
    await _ui_update(cb.message.bot, state, chat_id, "Шаг 8/10. Выберите категорию (до 2-х):", interests_kb([]))
    await cb.answer("⏭ Максимальная цена пропущена")


@router.message(UGCFormStates.entering_price_max, F.text)
async def form_price_max(message: Message, state: FSMContext) -> None:
    txt = (message.text or "").strip()
    if not re.fullmatch(r"\d+", txt):
        await message.answer("❌ Введите число")
        return
    await state.update_data(price_max=int(txt))
    await state.set_state(UGCFormStates.choosing_category)
    data = await state.get_data()
    stack = list(data.get("_flow_stack", []))
    stack.append("choosing_category")
    await state.update_data(_flow_stack=stack, selected_categories=[])
    await _ui_update(message.bot, state, message.chat.id, "Шаг 8/10. Выберите категорию (до 2-х):", interests_kb([]))


@router.callback_query(UGCFormStates.choosing_category, F.data.startswith("int:"))
async def form_category(cb: CallbackQuery, state: FSMContext) -> None:
    _, cat = (cb.data or "").split(":", 1)
    data = await state.get_data()
    selected = list(data.get("selected_categories", []))

    if cat == "done":
        if not selected:
            await cb.answer("❌ Выберите хотя бы одну категорию", show_alert=True)
            return
        # Save first category as main category
        await state.update_data(category=selected[0])
        await state.set_state(UGCFormStates.entering_link)
        stack = list(data.get("_flow_stack", []))
        stack.append("entering_link")
        await state.update_data(_flow_stack=stack)
        chat_id = cb.message.chat.id if cb.message and cb.message.chat else 0
        await _ui_update(cb.message.bot, state, chat_id, "Шаг 9/10. Ссылка на источник:", kb_back(skip_cb="form:skip:link"))
        await cb.answer()
        return

    # Toggle category selection
    if cat in selected:
        selected.remove(cat)
        await cb.answer("❌ Категория убрана")
    else:
        if len(selected) >= 2:
            await cb.answer("⚠️ Можно выбрать максимум 2 категории", show_alert=True)
            return
        selected.append(cat)
        await cb.answer("✅ Категория добавлена")

    await state.update_data(selected_categories=selected)

    # Update keyboard with new selection
    chat_id = cb.message.chat.id if cb.message and cb.message.chat else 0
    await _ui_update(cb.message.bot, state, chat_id, "Шаг 8/10. Выберите категорию (до 2-х):", interests_kb(selected))


@router.callback_query(UGCFormStates.entering_link, F.data == "form:skip:link")
async def skip_link(cb: CallbackQuery, state: FSMContext) -> None:
    """Skip link field."""
    await state.update_data(source_url="")
    await state.set_state(UGCFormStates.adding_photos)
    data = await state.get_data()
    stack = list(data.get("_flow_stack", []))
    stack.append("adding_photos")
    await state.update_data(_flow_stack=stack)
    chat_id = cb.message.chat.id if cb.message and cb.message.chat else 0
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Готово", callback_data="form:photos_done")],[InlineKeyboardButton(text="⬅️ Назад", callback_data="form:back")],[InlineKeyboardButton(text="✖️ Отмена", callback_data="form:cancel")]])
    await _ui_update(cb.message.bot, state, chat_id, "Шаг 10/10. Пришлите фото (можно до 10 штук одновременно). Когда закончите, нажмите 'Готово'.", kb)
    await cb.answer("⏭ Ссылка пропущена")


@router.message(UGCFormStates.entering_link, F.text)
async def form_link(message: Message, state: FSMContext) -> None:
    txt = (message.text or "").strip()
    await state.update_data(source_url=txt)
    await state.set_state(UGCFormStates.adding_photos)
    data = await state.get_data()
    stack = list(data.get("_flow_stack", []))
    stack.append("adding_photos")
    await state.update_data(_flow_stack=stack)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Готово", callback_data="form:photos_done")],[InlineKeyboardButton(text="⬅️ Назад", callback_data="form:back")],[InlineKeyboardButton(text="✖️ Отмена", callback_data="form:cancel")]])
    await _ui_update(message.bot, state, message.chat.id, "Шаг 10/10. Пришлите фото (можно до 10 штук одновременно). Когда закончите, нажмите 'Готово'.", kb)


async def _download_tg_file(file_id: str) -> str:
    s = get_settings()
    token = s.bot_token
    base = f"https://api.telegram.org/bot{token}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(f"{base}/getFile", params={"file_id": file_id})
        r.raise_for_status()
        fp = r.json().get("result", {}).get("file_path")
        file_url = f"https://api.telegram.org/file/bot{token}/{fp}"
        img = await client.get(file_url)
        img.raise_for_status()
        uploads = Path(__file__).resolve().parents[2] / "admin" / "static" / "uploads"
        uploads.mkdir(parents=True, exist_ok=True)
        ext = Path(fp).suffix or ".jpg"
        fname = f"ugc_{uuid.uuid4().hex}{ext}"
        dest = uploads / fname
        dest.write_bytes(img.content)
        return f"/static/uploads/{fname}"  # Admin app mounts /static, not /admin/static


@router.message(UGCFormStates.adding_photos, F.photo)
async def form_photos_collect(message: Message, state: FSMContext, album: list[Message] | None = None) -> None:
    """
    Collect photos - supports both single photos and media groups (albums).

    The album parameter is injected by AlbumMiddleware when multiple photos are sent together.
    """
    try:
        # Get current state
        data = await state.get_data()
        images = list(data.get("images", []))

        # Check limit
        if len(images) >= 10:
            await message.answer("❌ Достигнут лимит: максимум 10 фото. Нажмите 'Готово' чтобы продолжить.")
            return

        # Keyboard with action buttons
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Готово", callback_data="form:photos_done")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="form:back")],
            [InlineKeyboardButton(text="✖️ Отмена", callback_data="form:cancel")]
        ])

        # Get current file_ids list (for carousel preview)
        file_ids_list = list(data.get("file_ids", []))

        if album:
            # MEDIA GROUP (album) - middleware collected all photos for us!
            # Extract all file_ids from the album
            telegram_file_ids = [msg.photo[-1].file_id for msg in album]

            # Check how many we can actually add
            available_slots = 10 - len(images)
            file_ids_to_process = telegram_file_ids[:available_slots]

            if not file_ids_to_process:
                await message.answer("❌ Достигнут лимит: максимум 10 фото.", reply_markup=kb)
                return

            # Download all photos in parallel
            download_tasks = [_download_tg_file(fid) for fid in file_ids_to_process]
            urls = await asyncio.gather(*download_tasks, return_exceptions=True)

            # Filter successful downloads
            valid_urls = [u for u in urls if isinstance(u, str)]

            if valid_urls:
                # Add URLs to images (for admin panel)
                new_images = images + valid_urls
                # Add file_ids (for bot carousel preview)
                new_file_ids = file_ids_list + file_ids_to_process
                await state.update_data(images=new_images, file_ids=new_file_ids)

                await message.answer(
                    f"✅ Добавлено фото: {len(valid_urls)} шт. Всего: {len(new_images)}/10\n\n"
                    f"Пришлите ещё фото или нажмите 'Готово' для продолжения.",
                    reply_markup=kb
                )
            else:
                await message.answer("❌ Не удалось загрузить фото. Попробуйте ещё раз.", reply_markup=kb)

        else:
            # SINGLE PHOTO - process immediately
            best = message.photo[-1]
            telegram_file_id = best.file_id
            url = await _download_tg_file(telegram_file_id)
            images.append(url)
            file_ids_list.append(telegram_file_id)
            await state.update_data(images=images, file_ids=file_ids_list)
            await message.answer(
                f"✅ Фото добавлено. Всего: {len(images)}/10\n\n"
                f"Пришлите ещё фото или нажмите 'Готово' для продолжения.",
                reply_markup=kb
            )

    except Exception as e:
        await message.answer("Не получилось сохранить фото. Пришлите другое или нажмите 'Готово'.")


# Fallback handler for non-photo messages in adding_photos state
@router.message(UGCFormStates.adding_photos)
async def form_photos_invalid(message: Message, state: FSMContext) -> None:
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Готово", callback_data="form:photos_done")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="form:back")],
        [InlineKeyboardButton(text="✖️ Отмена", callback_data="form:cancel")]
    ])
    await message.answer("❌ Пожалуйста, пришлите фото или нажмите 'Готово' для продолжения.", reply_markup=kb)


@router.callback_query(UGCFormStates.adding_photos, F.data == "form:photos_done")
async def form_photos_done(cb: CallbackQuery, state: FSMContext) -> None:
    from aiogram.types import InputMediaPhoto, FSInputFile

    data = await state.get_data()
    title = data.get("title", "")
    date_iso = data.get("date_iso") or ""
    time_24h = data.get("time_24h") or ""
    venue = data.get("venue_name") or ""
    address = data.get("address") or ""
    city = data.get("city") or ""
    price_min = data.get("price_min")
    price_max = data.get("price_max")
    category = data.get("category") or ""
    source_url = data.get("source_url") or ""
    images = list(data.get("images", []))

    text = (
        "📋 Предпросмотр:\n\n"
        f"📌 Название: {title}\n"
        f"📅 Дата: {date_iso} {time_24h}\n"
        f"🏙 Город: {city}\n"
        f"📍 Адрес: {address}\n"
        f"💰 Цена: {(price_min or '')}-{(price_max or '')}\n"
        f"🏷 Категория: {category}\n"
        f"🔗 Ссылка: {source_url}\n"
        f"📸 Фото: {len(images)} шт.\n\n"
        f"Отправить на модерацию?"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Отправить", callback_data="form:send")],
            [InlineKeyboardButton(text="Изменить название", callback_data="form:edit:title"), InlineKeyboardButton(text="Изменить дату/время", callback_data="form:edit:dt")],
            [InlineKeyboardButton(text="Изменить город", callback_data="form:edit:city"), InlineKeyboardButton(text="Изменить адрес", callback_data="form:edit:addr")],
            [InlineKeyboardButton(text="Изменить цену", callback_data="form:edit:price"), InlineKeyboardButton(text="Изменить категорию", callback_data="form:edit:cat")],
            [InlineKeyboardButton(text="Изменить ссылку", callback_data="form:edit:link"), InlineKeyboardButton(text="Добавить фото", callback_data="form:edit:photos")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="form:back")],
            [InlineKeyboardButton(text="✖️ Отмена", callback_data="form:cancel")],
        ]
    )

    await state.set_state(UGCFormStates.confirming)
    chat_id = cb.message.chat.id if cb.message and cb.message.chat else 0

    # Send photos as media group (carousel) with caption on first photo
    file_ids = list(data.get("file_ids", []))

    if file_ids:
        # Use Telegram file_ids for carousel (no need to download)
        media = []

        for idx, file_id in enumerate(file_ids[:10]):  # Max 10 photos in media group
            # First photo gets caption
            if idx == 0:
                media.append(InputMediaPhoto(media=file_id, caption=text))
            else:
                media.append(InputMediaPhoto(media=file_id))

        # Send media group
        try:
            sent_messages = await cb.message.bot.send_media_group(chat_id, media)
        except Exception as e:
            # If media group fails, fallback to text only
            await _ui_update(cb.message.bot, state, chat_id, text + f"\n\n(Ошибка отправки фото)", kb, force_new=True)
            await cb.answer()
            return

        # Send message with buttons (media group can't have inline keyboard)
        msg = await cb.message.bot.send_message(
            chat_id,
            "Выберите действие:",
            reply_markup=kb
        )
        await state.update_data(_ui_msg_id=msg.message_id, _ui_chat_id=chat_id, _last_kb_was_reply=False)
    else:
        # No photos - send text message only
        await _ui_update(cb.message.bot, state, chat_id, text, kb, force_new=True)

    await cb.answer()


@router.callback_query(UGCFormStates.confirming, F.data == "form:send")
async def form_send(cb: CallbackQuery, state: FSMContext) -> None:
    # Ask about paid promotion first
    await state.set_state(UGCFormStates.choosing_paid_promotion)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, хочу платное продвижение", callback_data="promo:yes")],
            [InlineKeyboardButton(text="❌ Нет, бесплатно", callback_data="promo:no")],
        ]
    )
    chat_id = cb.message.chat.id if cb.message and cb.message.chat else 0
    await _ui_update(
        cb.message.bot,
        state,
        chat_id,
        "💰 Хотите ли вы купить продвижение для вашего события?\n\n"
        "Платное размещение даст:\n"
        "• Приоритетный показ в ленте\n"
        "• Больше просмотров и переходов\n"
        "• Специальную отметку 🔥",
        kb
    )
    await cb.answer()


@router.callback_query(UGCFormStates.choosing_paid_promotion, F.data.startswith("promo:"))
async def form_paid_promotion(cb: CallbackQuery, state: FSMContext) -> None:
    _, choice = (cb.data or "").split(":", 1)
    data = await state.get_data()

    wants_paid = choice == "yes"

    if wants_paid:
        # NEW: Redirect to paid placement flow with monetization
        from app.bot.states import PaidPlacementStates

        msg = """
Выберите тип продвижения для вашего события:

🌍 **Весь Крым** - охват всех пользователей (максимальная аудитория)
🏙 **Мой город** - только пользователи вашего города (средний охват)
📍 **Мой район** - пользователи вашего района (таргетированный охват)
🔥 **Горящее** - срочная публикация в течение 2 часов (фиксированная цена)

💡 *Цена рассчитывается автоматически на основе охвата и времени до события.*
"""

        from app.bot.handlers.paid_placement import placement_type_kb

        await cb.message.edit_text(msg, reply_markup=placement_type_kb())
        await state.set_state(PaidPlacementStates.choosing_type)
        await cb.answer()
        return

    # Free placement - old logic
    form = {
        "title": data.get("title"),
        "date_iso": data.get("date_iso"),
        "time_24h": data.get("time_24h"),
        "city": data.get("city"),
        "address": data.get("address"),
        "lat": data.get("lat"),
        "lon": data.get("lon"),
        "price_min": data.get("price_min"),
        "price_max": data.get("price_max"),
        "category": data.get("category"),
        "source_url": data.get("source_url"),
    }
    payload = {
        "raw_text": f"FORM:{form}",
        "form": form,
        "wants_paid_promotion": False,
    }
    images = list(data.get("images", []))
    if images:
        payload["images"] = images
    if cb.from_user:
        payload["user_id"] = cb.from_user.id

    await api_ugc_submit(payload)  # type: ignore[arg-type]

    msg = "✅ Заявка отправлена на модерацию!\n\nМы проверим её и опубликуем в ближайшее время."

    from app.bot.keyboards.common import main_menu_kb

    await cb.message.edit_text(msg)
    await state.clear()
    await cb.message.answer("Выберите действие:", reply_markup=main_menu_kb())
    await cb.answer()


@router.callback_query(UGCFormStates.confirming, F.data == "form:cancel")
async def form_cancel(cb: CallbackQuery, state: FSMContext) -> None:
    from app.bot.keyboards.common import main_menu_kb

    await state.clear()
    chat_id = cb.message.chat.id if cb.message and cb.message.chat else 0
    await _ui_update(cb.message.bot, state, chat_id, "Отменено.")
    await cb.message.answer("Выберите действие:", reply_markup=main_menu_kb())
    await cb.answer()


# Навигация "Назад": берём предыдущий шаг из стека и повторяем вопрос
@router.callback_query(F.data == "form:back")
async def form_back(cb: CallbackQuery, state: FSMContext) -> None:
    if not cb.message or not cb.message.chat:
        await cb.answer()
        return
    chat_id = cb.message.chat.id
    data = await state.get_data()
    stack = list(data.get("_flow_stack", []))
    # текущий шаг = последний, назад = предпоследний
    if len(stack) > 1:
        stack.pop()  # remove current
        prev = stack[-1]
        await state.update_data(_flow_stack=stack)
        # route to prev
        if prev == "entering_title":
            await state.set_state(UGCFormStates.entering_title)
            await _ui_update(cb.message.bot, state, chat_id, "Шаг 1/10. Введите название события:", kb_back())
        elif prev == "entering_date":
            await state.set_state(UGCFormStates.entering_date)
            await _ui_update(cb.message.bot, state, chat_id, "Шаг 2/10. Дата (ГГГГ-ММ-ДД) или напишите 'пропустить':", kb_back())
        elif prev == "entering_time":
            await state.set_state(UGCFormStates.entering_time)
            await _ui_update(cb.message.bot, state, chat_id, "Шаг 3/10. Время (ЧЧ:ММ) или 'пропустить':", kb_back())
        elif prev == "choosing_city":
            await state.set_state(UGCFormStates.choosing_city)
            await _ui_update(cb.message.bot, state, chat_id, "Шаг 4/10. Выберите город:", cities_kb())
        elif prev == "entering_address":
            await state.set_state(UGCFormStates.entering_address)
            await _ui_update(cb.message.bot, state, chat_id, "Шаг 5/10. Укажите адрес текстом или отправьте геолокацию:", request_location_kb())
        elif prev == "entering_price_min":
            await state.set_state(UGCFormStates.entering_price_min)
            await _ui_update(cb.message.bot, state, chat_id, "Шаг 6/10. Минимальная цена (число) или 'пропустить':", kb_back())
        elif prev == "entering_price_max":
            await state.set_state(UGCFormStates.entering_price_max)
            await _ui_update(cb.message.bot, state, chat_id, "Шаг 7/10. Максимальная цена (число) или 'пропустить':", kb_back())
        elif prev == "choosing_category":
            await state.set_state(UGCFormStates.choosing_category)
            await _ui_update(cb.message.bot, state, chat_id, "Шаг 8/10. Выберите категорию:", interests_kb())
        elif prev == "entering_link":
            await state.set_state(UGCFormStates.entering_link)
            await _ui_update(cb.message.bot, state, chat_id, "Шаг 9/10. Ссылка на источник (или 'пропустить'):", kb_back())
        elif prev == "adding_photos":
            await state.set_state(UGCFormStates.adding_photos)
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Готово", callback_data="form:photos_done")],[InlineKeyboardButton(text="⬅️ Назад", callback_data="form:back")],[InlineKeyboardButton(text="✖️ Отмена", callback_data="form:cancel")]])
            await _ui_update(cb.message.bot, state, chat_id, "Шаг 10/10. Пришлите фото (можно до 10 штук одновременно). Когда закончите, нажмите 'Готово'.", kb)
    await cb.answer()


# Редактирование из предпросмотра: переводим на нужный шаг
@router.callback_query(UGCFormStates.confirming, F.data.startswith("form:edit:"))
async def form_edit(cb: CallbackQuery, state: FSMContext) -> None:
    target = (cb.data or "").split(":", 2)[2]
    data = await state.get_data()
    stack = list(data.get("_flow_stack", []))
    if target == "title":
        await state.set_state(UGCFormStates.entering_title)
        stack.append("entering_title")
        await state.update_data(_flow_stack=stack)
        await _ui_update(cb.message.bot, state, cb.message.chat.id, "Введите название события:", kb_back())
    elif target == "dt":
        await state.set_state(UGCFormStates.entering_date)
        stack.append("entering_date")
        await state.update_data(_flow_stack=stack)
        await _ui_update(cb.message.bot, state, cb.message.chat.id, "Дата (ГГГГ-ММ-ДД) или 'пропустить':", kb_back())
    elif target == "city":
        await state.set_state(UGCFormStates.choosing_city)
        stack.append("choosing_city")
        await state.update_data(_flow_stack=stack)
        await _ui_update(cb.message.bot, state, cb.message.chat.id, "Выберите город:", cities_kb())
    elif target == "addr":
        await state.set_state(UGCFormStates.entering_address)
        stack.append("entering_address")
        await state.update_data(_flow_stack=stack)
        await _ui_update(cb.message.bot, state, cb.message.chat.id, "Укажите адрес текстом или отправьте геолокацию:", request_location_kb())
    elif target == "price":
        await state.set_state(UGCFormStates.entering_price_min)
        stack.append("entering_price_min")
        await state.update_data(_flow_stack=stack)
        await _ui_update(cb.message.bot, state, cb.message.chat.id, "Минимальная цена (число) или 'пропустить':", kb_back())
    elif target == "cat":
        await state.set_state(UGCFormStates.choosing_category)
        stack.append("choosing_category")
        await state.update_data(_flow_stack=stack)
        await _ui_update(cb.message.bot, state, cb.message.chat.id, "Выберите категорию:", interests_kb())
    elif target == "link":
        await state.set_state(UGCFormStates.entering_link)
        stack.append("entering_link")
        await state.update_data(_flow_stack=stack)
        await _ui_update(cb.message.bot, state, cb.message.chat.id, "Ссылка на источник (или 'пропустить'):", kb_back())
    elif target == "photos":
        await state.set_state(UGCFormStates.adding_photos)
        stack.append("adding_photos")
        await state.update_data(_flow_stack=stack)
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Готово", callback_data="form:photos_done")],[InlineKeyboardButton(text="⬅️ Назад", callback_data="form:back")]])
        await _ui_update(cb.message.bot, state, cb.message.chat.id, "Пришлите фото (можно до 10 штук одновременно). Когда закончите, нажмите 'Готово'.", kb)
    await cb.answer()

