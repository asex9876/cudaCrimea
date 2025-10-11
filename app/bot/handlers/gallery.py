from __future__ import annotations

from typing import Any, Dict, Tuple

from aiogram import F, Router
from aiogram.types import CallbackQuery, InputMediaPhoto
import httpx

from app.core.config import get_settings


router = Router()

# In-memory carousel state: key=(chat_id, message_id) -> {"event_id": str, "images": [str], "idx": int}
CAROUSELS: Dict[Tuple[int, int], Dict[str, Any]] = {}


async def _fetch_event_images(event_id: str) -> list[str]:
    s = get_settings()
    url = f"http://{s.api_host}:{s.api_port}/api/events/{event_id}/images"
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(url)
        r.raise_for_status()
        data = r.json()
        imgs = data.get("images", [])
        return [i for i in imgs if isinstance(i, str) and i]


async def _ensure_carousel(cb: CallbackQuery, event_id: str) -> Dict[str, Any]:
    key = (cb.message.chat.id if cb.message and cb.message.chat else 0, cb.message.message_id if cb.message else 0)
    st = CAROUSELS.get(key)
    if not st or st.get("event_id") != event_id:
        images = await _fetch_event_images(event_id)
        if not images:
            images = []
        st = {"event_id": event_id, "images": images, "idx": 0}
        CAROUSELS[key] = st
    return st


@router.callback_query(F.data.startswith("img:"))
async def on_img_nav(cb: CallbackQuery) -> None:
    parts = (cb.data or "").split(":")
    # img:<dir>:event:<id>
    if len(parts) != 4:
        await cb.answer()
        return
    _, direction, _etype, eid = parts
    state = await _ensure_carousel(cb, eid)
    images: list[str] = state.get("images", [])
    if not images or not cb.message:
        await cb.answer("Нет фото")
        return
    idx = state.get("idx", 0)
    if direction == "next":
        idx = (idx + 1) % len(images)
    elif direction == "prev":
        idx = (idx - 1) % len(images)
    state["idx"] = idx
    # Keep existing caption and keyboard
    caption = cb.message.caption or None
    media = InputMediaPhoto(media=images[idx], caption=caption)
    try:
        await cb.message.edit_media(media=media, reply_markup=cb.message.reply_markup)
        await cb.answer()
    except Exception:
        await cb.answer("Не удалось обновить фото")

