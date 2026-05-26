from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.client import api_search
from app.bot.context import get_user_city
from app.bot.keyboards.common import INTEREST_CATEGORIES, event_actions_kb_with_back, interests_kb, when_kb
from app.bot.states import WhatToDoStates
from app.bot.utils.render import render_event_card
from app.core.services.geo import yandex_deeplink


router = Router()


def _budget_prompt_text(error: bool = False) -> str:
    base = "Укажите бюджет (только число) или 0 если не важно"
    if error:
        return "Не получилось распознать бюджет. " + base
    return base


def _budget_kb() -> InlineKeyboardMarkup:
    """Keyboard for budget input with Back button."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="wtd:back")]
    ])


async def _wtd_ui_update(
    bot,
    state: FSMContext,
    chat_id: int,
    text: str,
    kb: InlineKeyboardMarkup | None = None,
) -> None:
    import structlog
    logger = structlog.get_logger()

    data = await state.get_data()
    ui = data.get("_wtd_ui")
    if ui is None:
        m = await bot.send_message(chat_id, text, reply_markup=kb)
        await state.update_data(_wtd_ui={"msg_id": m.message_id, "chat_id": chat_id})
        logger.info("wtd.ui.new_message", msg_id=m.message_id)
        return
    try:
        await bot.edit_message_text(
            chat_id=ui["chat_id"],
            message_id=ui["msg_id"],
            text=text,
            reply_markup=kb,
        )
        logger.info("wtd.ui.edited", msg_id=ui["msg_id"])
    except Exception as e:
        logger.error("wtd.ui.edit_failed", msg_id=ui.get("msg_id"), error=str(e))
        # Try sending new message as fallback
        m = await bot.send_message(chat_id, text, reply_markup=kb)
        await state.update_data(_wtd_ui={"msg_id": m.message_id, "chat_id": chat_id})
        logger.info("wtd.ui.sent_new_instead", msg_id=m.message_id)


def _render_interests_prompt(selected: set[str], with_back: bool = True) -> tuple[str, InlineKeyboardMarkup]:
    selected_names = [label for label, slug in INTEREST_CATEGORIES if slug in selected]
    prompt = "Выберите интересы (можно несколько), затем нажмите «Готово»"
    if selected_names:
        prompt += "\n\nВыбрано: " + ", ".join(selected_names)
    return prompt, interests_kb(selected, with_back=with_back)


def _prepare_event(raw: dict[str, Any]) -> dict[str, Any]:
    event = dict(raw)
    deeplink = event.get("deeplink")
    if not deeplink:
        lat = event.get("lat")
        lon = event.get("lon")
        title = event.get("title")
        if lat and lon:
            deeplink = yandex_deeplink(lat, lon, title)
    if deeplink:
        event["deeplink"] = deeplink
    return event


def _event_keyboard(event: dict[str, Any], idx: int, total: int) -> InlineKeyboardMarkup:
    event_id = str(event.get("id") or "")
    base = event_actions_kb_with_back(event_id, event.get("deeplink") or "", event.get("source_url"))
    base_rows = [list(row) for row in (base.inline_keyboard or [])]
    image_url = event.get("image_url")
    # Only add photo button if URL is absolute (starts with http:// or https://)
    if image_url and (image_url.startswith("http://") or image_url.startswith("https://")):
        base_rows.append([InlineKeyboardButton(text="Фото", url=image_url)])
    page_label = f"{idx + 1}/{total}" if total else "0/0"
    if total > 1:
        nav_row = [
            InlineKeyboardButton(text="<", callback_data="wtd:prev"),
            InlineKeyboardButton(text=page_label, callback_data="wtd:noop"),
            InlineKeyboardButton(text=">", callback_data="wtd:next"),
        ]
    else:
        nav_row = [InlineKeyboardButton(text=page_label, callback_data="wtd:noop")]
    base_rows.append(nav_row)
    return InlineKeyboardMarkup(inline_keyboard=base_rows)


def _render_event_text(event: dict[str, Any], idx: int, total: int) -> str:
    header = f"Событие {idx + 1} из {total}" if total else "События отсутствуют"
    card = render_event_card(SimpleNamespace(**event))
    parts = [header, card]
    site = event.get("source_url")
    if site:
        parts.append(f"Сайт: {site}")
    deeplink = event.get("deeplink")
    if deeplink:
        parts.append(f"Маршрут: {deeplink}")
    if event.get("image_url"):
        parts.append("Фото: воспользуйтесь кнопкой ниже.")
    return "\n\n".join(parts)


async def _wtd_show_event(bot, state: FSMContext, chat_id: int, index: int) -> None:
    data = await state.get_data()
    events = data.get("_wtd_events") or []
    if not events:
        prompt, kb = _render_interests_prompt(set(data.get("interests", [])))
        await _wtd_ui_update(bot, state, chat_id, "Ничего не нашли. Попробуйте изменить выбор.", kb)
        await state.set_state(WhatToDoStates.choosing_interests)
        return
    total = len(events)
    index = index % total
    event = events[index]
    await state.update_data(_wtd_event_idx=index)
    text = _render_event_text(event, index, total)
    kb = _event_keyboard(event, index, total)
    await _wtd_ui_update(bot, state, chat_id, text, kb)


@router.message(F.text == "🎤 Куда сходить")
async def ask_when(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(WhatToDoStates.choosing_when)
    m = await message.answer("Когда пойдём?", reply_markup=when_kb())
    await state.update_data(_wtd_ui={"msg_id": m.message_id, "chat_id": message.chat.id})


@router.callback_query(WhatToDoStates.choosing_when, F.data.startswith("when:"))
async def choose_when(cb: CallbackQuery, state: FSMContext) -> None:
    if not cb.message or not cb.message.chat:
        await cb.answer()
        return
    when = (cb.data or "").split(":", 1)[1]
    await state.update_data(when=when)

    # For "hot" events, skip budget and interests - show results immediately
    if when == "hot":
        chat_id = cb.message.chat.id
        await cb.answer("Ищу горячие события…")
        await _wtd_ui_update(cb.message.bot, state, chat_id, "Ищу горячие события…")
        city = await get_user_city(cb.from_user.id if cb.from_user else 0)
        params = {"city": city, "when": "hot", "budget_max": None, "categories": None}
        try:
            resp = await api_search(params)
        except Exception:
            await _wtd_ui_update(cb.message.bot, state, chat_id, "Сервис временно недоступен. Попробуйте позже.", when_kb())
            return
        raw_events = resp.get("events", [])[:5]
        events = [_prepare_event(e) for e in raw_events if isinstance(e, dict)]
        if not events:
            await _wtd_ui_update(cb.message.bot, state, chat_id, "Горячих событий не найдено. Попробуйте другую дату.", when_kb())
            return
        await state.update_data(_wtd_events=events)
        await state.set_state(WhatToDoStates.showing_results)
        await _wtd_show_event(cb.message.bot, state, chat_id, 0)
        return

    # For other options, continue with budget selection
    await state.set_state(WhatToDoStates.entering_budget)
    await _wtd_ui_update(cb.message.bot, state, cb.message.chat.id, _budget_prompt_text(), _budget_kb())
    await cb.answer()


@router.message(WhatToDoStates.entering_budget, F.text.regexp(r"^\d+$"))
async def enter_budget(message: Message, state: FSMContext) -> None:
    budget = int(message.text)
    await state.update_data(budget=budget if budget > 0 else None)
    await state.set_state(WhatToDoStates.choosing_interests)
    data = await state.get_data()
    selected = set(data.get("interests", []))
    text, kb = _render_interests_prompt(selected)
    await _wtd_ui_update(message.bot, state, message.chat.id, text, kb)


@router.message(WhatToDoStates.entering_budget)
async def enter_budget_invalid(message: Message, state: FSMContext) -> None:
    chat = message.chat
    if not chat:
        return
    await _wtd_ui_update(message.bot, state, chat.id, _budget_prompt_text(error=True), _budget_kb())


@router.callback_query(WhatToDoStates.choosing_interests, F.data.startswith("int:"))
async def choose_interests(cb: CallbackQuery, state: FSMContext) -> None:
    if not cb.message or not cb.message.chat:
        await cb.answer()
        return
    _, val = (cb.data or "").split(":", 1)
    data = await state.get_data()
    chosen = set(data.get("interests", []))
    chat_id = cb.message.chat.id
    if val == "done":
        await state.update_data(interests=list(chosen))
        await cb.answer("Ищу варианты…")
        await _wtd_ui_update(cb.message.bot, state, chat_id, "Ищу варианты…")
        when = data.get("when", "today")
        budget = data.get("budget")
        city = await get_user_city(cb.from_user.id if cb.from_user else 0)
        params = {"city": city, "when": when, "budget_max": budget, "categories": list(chosen) or None}
        try:
            resp = await api_search(params)
        except Exception:
            text, kb = _render_interests_prompt(chosen)
            await _wtd_ui_update(cb.message.bot, state, chat_id, "Сервис временно недоступен. Попробуйте позже.", kb)
            return
        raw_events = resp.get("events", [])[:5]
        events = [_prepare_event(e) for e in raw_events if isinstance(e, dict)]
        if not events:
            text, kb = _render_interests_prompt(chosen)
            await _wtd_ui_update(cb.message.bot, state, chat_id, "Ничего не нашли. Попробуйте изменить выбор.", kb)
            return
        await state.update_data(_wtd_events=events)
        await state.set_state(WhatToDoStates.showing_results)
        await _wtd_show_event(cb.message.bot, state, chat_id, 0)
        return

    if val in chosen:
        chosen.remove(val)
    else:
        chosen.add(val)
    await state.update_data(interests=list(chosen))
    text, kb = _render_interests_prompt(chosen)
    await _wtd_ui_update(cb.message.bot, state, chat_id, text, kb)
    await cb.answer()


async def _shift_results(cb: CallbackQuery, state: FSMContext, delta: int) -> None:
    if not cb.message or not cb.message.chat:
        await cb.answer()
        return
    data = await state.get_data()
    events = data.get("_wtd_events") or []
    if not events:
        await cb.answer("Нет событий")
        return
    current = data.get("_wtd_event_idx", 0)
    index = (current + delta) % len(events)
    await _wtd_show_event(cb.message.bot, state, cb.message.chat.id, index)
    await cb.answer()


@router.callback_query(WhatToDoStates.showing_results, F.data == "wtd:next")
async def results_next(cb: CallbackQuery, state: FSMContext) -> None:
    await _shift_results(cb, state, 1)


@router.callback_query(WhatToDoStates.showing_results, F.data == "wtd:prev")
async def results_prev(cb: CallbackQuery, state: FSMContext) -> None:
    await _shift_results(cb, state, -1)


@router.callback_query(F.data == "wtd:noop")
async def results_noop(cb: CallbackQuery) -> None:
    await cb.answer()


@router.callback_query(F.data == "wtd:back")
async def wtd_back(cb: CallbackQuery, state: FSMContext) -> None:
    """Handle Back button in what-to-do flow."""
    if not cb.message or not cb.message.chat:
        await cb.answer()
        return

    current_state = await state.get_state()
    chat_id = cb.message.chat.id

    # Budget -> When
    if current_state == WhatToDoStates.entering_budget:
        await state.set_state(WhatToDoStates.choosing_when)
        await _wtd_ui_update(cb.message.bot, state, chat_id, "Когда пойдём?", when_kb())
        await cb.answer("⬅️ Возврат к выбору даты")

    # Interests -> Budget
    elif current_state == WhatToDoStates.choosing_interests:
        await state.set_state(WhatToDoStates.entering_budget)
        await _wtd_ui_update(cb.message.bot, state, chat_id, _budget_prompt_text(), _budget_kb())
        await cb.answer("⬅️ Возврат к вводу бюджета")

    # Results -> Interests
    elif current_state == WhatToDoStates.showing_results:
        data = await state.get_data()
        selected = set(data.get("interests", []))
        text, kb = _render_interests_prompt(selected)
        await state.set_state(WhatToDoStates.choosing_interests)
        await _wtd_ui_update(cb.message.bot, state, chat_id, text, kb)
        await cb.answer("⬅️ Возврат к выбору интересов")

    else:
        await cb.answer()
