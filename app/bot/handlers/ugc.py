from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from pathlib import Path
import uuid
import httpx

from app.bot.client import api_ugc_submit
from app.bot.states import UGCStates
from app.core.llm.extractor import EventDraft, extract_event_fields
from app.core.config import get_settings


router = Router()


@router.message(F.text == "➕ Добавить событие")
async def ugc_start(message: Message, state: FSMContext) -> None:
    await state.set_state(UGCStates.entering_text)
    await message.answer("Пришлите текст анонса события (можно с ссылкой)")


@router.message(UGCStates.entering_text, F.text)
async def ugc_process(message: Message, state: FSMContext) -> None:
    raw = message.text or ""
    draft: EventDraft = extract_event_fields(raw, None)
    # keep both original raw text and extracted draft for confirm step
    await state.update_data(draft=draft.model_dump(), raw=raw)
    text = (
        "Предпросмотр:\n"
        f"Название: {draft.title}\nДата: {draft.date_iso} {draft.time_24h or ''}\n"
        f"Место: {draft.venue_name or ''}\nАдрес: {draft.address or ''}\n"
        f"Цена: {draft.price_min or ''}–{draft.price_max or ''}\nКатегория: {draft.category or ''}\n"
        f"Ссылка: {draft.source_url or ''}\n\nОтправить на модерацию?"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Отправить", callback_data="ugc:send")]])
    await state.set_state(UGCStates.confirming)
    await message.answer(text, reply_markup=kb)
    # Extra controls to manage photos before submit
    controls_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Добавить фото", callback_data="ugc:add_photos")],
            [InlineKeyboardButton(text="Очистить фото", callback_data="ugc:clear_photos")],
            [InlineKeyboardButton(text="Отправить", callback_data="ugc:send")],
        ]
    )
    await message.answer("Вы можете добавить/очистить фото перед отправкой:", reply_markup=controls_kb)


@router.callback_query(UGCStates.confirming, F.data == "ugc:send")
async def ugc_send(cb: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    draft = data.get("draft", {})
    raw_text = data.get("raw", "")
    source_url = draft.get("source_url") if isinstance(draft, dict) else None
    payload = {"raw_text": raw_text}
    if source_url:
        payload["source_url"] = source_url
    images = data.get("images") or ([] if not data.get("image_url") else [data.get("image_url")])
    if images:
        payload["images"] = images
    # attach user id
    if cb.from_user:
        payload["user_id"] = cb.from_user.id
    await api_ugc_submit(payload)
    await cb.message.edit_text("Спасибо! Заявка отправлена на модерацию.")
    await state.clear()
    await cb.answer()


@router.callback_query(UGCStates.confirming, F.data == "ugc:add_photos")
async def ugc_add_photos(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(UGCStates.adding_photos)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Готово", callback_data="ugc:done_photos")]])
    await cb.message.edit_text("Пришлите одно или несколько фото. Когда закончите, нажмите 'Готово'.", reply_markup=kb)
    await cb.answer()


@router.callback_query(UGCStates.confirming, F.data == "ugc:clear_photos")
async def ugc_clear_photos(cb: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(images=[])
    await cb.answer("Фото очищены")


@router.message(UGCStates.adding_photos, F.photo)
async def ugc_add_photos_collect(message: Message, state: FSMContext) -> None:
    try:
        best = message.photo[-1]
        url = await _download_tg_file(best.file_id)
        data = await state.get_data()
        images = list(data.get("images", []))
        images.append(url)
        await state.update_data(images=images)
        await message.answer(f"Фото добавлено ({len(images)}). Пришлите ещё или нажмите 'Готово'.")
    except Exception:
        await message.answer("Не удалось сохранить фото. Пришлите другое или нажмите 'Готово'.")


@router.callback_query(UGCStates.adding_photos, F.data == "ugc:done_photos")
async def ugc_done_photos(cb: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    draft = data.get("draft", {})
    images = list(data.get("images", []))
    # Recompose preview similar to initial one
    try:
        d = EventDraft.model_validate(draft)
    except Exception:
        from app.core.llm.extractor import EventDraft as _ED
        d = _ED()
    text = (
        "Предпросмотр:\n"
        f"Название: {getattr(d, 'title', '')}\nДата: {getattr(d, 'date_iso', '')} {getattr(d, 'time_24h', '')}\n"
        f"Место: {getattr(d, 'venue_name', '')}\nАдрес: {getattr(d, 'address', '')}\n"
        f"Цена: {getattr(d, 'price_min', '')}-{getattr(d, 'price_max', '')}\nКатегория: {getattr(d, 'category', '')}\n"
        f"Ссылка: {getattr(d, 'source_url', '')}\n"
        f"Фото: {len(images)} шт.\n\nОтправить на модерацию?"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Добавить фото", callback_data="ugc:add_photos")],
            [InlineKeyboardButton(text="Очистить фото", callback_data="ugc:clear_photos")],
            [InlineKeyboardButton(text="Отправить", callback_data="ugc:send")],
        ]
    )
    await state.set_state(UGCStates.confirming)
    await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer()


@router.message(UGCStates.entering_text, F.photo)
async def ugc_photo(message: Message, state: FSMContext) -> None:
    try:
        best = message.photo[-1]
        file_id = best.file_id
        url = await _download_tg_file(file_id)
        await state.update_data(image_url=url)
        await message.answer("Фото добавлено. Теперь пришлите ссылку или описание события одним сообщением.")
    except Exception:
        await message.answer("Не удалось сохранить фото. Пришлите текст события, а фото добавите позже.")


async def _download_tg_file(file_id: str) -> str:
    s = get_settings()
    token = s.bot_token
    if not token:
        raise RuntimeError("BOT_TOKEN is not configured")
    base = f"https://api.telegram.org/bot{token}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(f"{base}/getFile", params={"file_id": file_id})
        r.raise_for_status()
        fp = r.json().get("result", {}).get("file_path")
        if not fp:
            raise RuntimeError("No file_path from Telegram")
        file_url = f"https://api.telegram.org/file/bot{token}/{fp}"
        img = await client.get(file_url)
        img.raise_for_status()
        uploads = Path(__file__).resolve().parents[2] / "admin" / "static" / "uploads"
        uploads.mkdir(parents=True, exist_ok=True)
        ext = Path(fp).suffix or ".jpg"
        fname = f"ugc_{uuid.uuid4().hex}{ext}"
        dest = uploads / fname
        dest.write_bytes(img.content)
        return f"/admin/static/uploads/{fname}"
