from __future__ import annotations

import asyncio
from typing import Any

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.client import api_poll_create


router = Router()


class _PollStore:
    polls: dict[int, dict[str, Any]] = {}


@router.message(F.text == "🗳 Опрос")
async def create_poll(message: Message) -> None:
    payload = {"city": "Севастополь", "when": "today", "budget_max": None, "lat": None, "lon": None}
    try:
        resp = await api_poll_create(payload)
    except Exception:
        await message.answer("Сервис опросов недоступен. Попробуйте позже.")
        return
    items = resp.get("items", [])[:3]
    if not items:
        await message.answer("Не удалось сформировать варианты.")
        return
    text = "Выберите вариант (15 минут):\n" + "\n".join(f"{i+1}. {x['title']} — {x['subtitle']}" for i, x in enumerate(items))
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=str(i + 1), callback_data=f"vote:{i}") for i in range(len(items))]]
    )
    msg = await message.answer(text, reply_markup=kb)
    _PollStore.polls[msg.message_id] = {"items": items, "votes": [0] * len(items)}

    async def finish_poll(mid: int) -> None:
        await asyncio.sleep(15 * 60)
        poll = _PollStore.polls.pop(mid, None)
        if not poll:
            return
        votes = poll["votes"]
        win_idx = max(range(len(votes)), key=lambda i: votes[i])
        winner = poll["items"][win_idx]
        await msg.edit_text(
            f"Побеждает: {winner['title']} — {winner['subtitle']}\nСсылка: {winner['button_url']}"
        )

    asyncio.create_task(finish_poll(msg.message_id))


@router.callback_query(F.data.startswith("vote:"))
async def on_vote(cb: CallbackQuery) -> None:
    msg_id = cb.message.message_id if cb.message else None
    if msg_id is None or msg_id not in _PollStore.polls:
        await cb.answer("Опрос завершён или недоступен", show_alert=True)
        return
    idx = int((cb.data or "0").split(":", 1)[1])
    _PollStore.polls[msg_id]["votes"][idx] += 1
    await cb.answer("Голос учтён")

