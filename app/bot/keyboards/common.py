from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from typing import Collection
from app.core import runtime_config as rc


def cities_kb() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="Севастополь"), KeyboardButton(text="Симферополь")],
        [KeyboardButton(text="Ялта"), KeyboardButton(text="Евпатория")],
        [KeyboardButton(text="Феодосия"), KeyboardButton(text="Керчь")],
        [KeyboardButton(text="Алушта"), KeyboardButton(text="Судак")],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, one_time_keyboard=True)


def request_location_kb() -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(text="Отправить геолокацию", request_location=True)]]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, one_time_keyboard=True)


def when_kb() -> InlineKeyboardMarkup:
    """Keyboard for date selection with 'Hot' events option."""
    buttons = [
        # Hot events - today's events that are still accessible
        [InlineKeyboardButton(text="🔥 Горячее", callback_data="when:hot")],
        # Quick options
        [
            InlineKeyboardButton(text="Сегодня", callback_data="when:today"),
            InlineKeyboardButton(text="Завтра", callback_data="when:tomorrow"),
        ],
        [
            InlineKeyboardButton(text="Вечером", callback_data="when:tonight"),
            InlineKeyboardButton(text="Выходные", callback_data="when:weekend"),
        ],
        # Extended period options
        [
            InlineKeyboardButton(text="На этой неделе", callback_data="when:this_week"),
            InlineKeyboardButton(text="В этом месяце", callback_data="when:this_month"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


INTEREST_CATEGORIES: list[tuple[str, str]] = [
    ("🎵 Концерты", "concert"),
    ("🎭 Театр", "theatre"),
    ("👶 Детям", "kids"),
    ("🗺 Экскурсии", "tour"),
    ("🎉 Вечеринки", "party"),
    ("🎨 Выставки", "expo"),
    ("📌 Другое", "other"),
]


def interests_kb(selected: Collection[str] | None = None) -> InlineKeyboardMarkup:
    selected_set = set(selected or [])
    rows = []
    for label, slug in INTEREST_CATEGORIES:
        checkmark = "✅ " if slug in selected_set else ""
        rows.append([InlineKeyboardButton(text=f"{checkmark}{label}", callback_data=f"int:{slug}")])
    rows.append([InlineKeyboardButton(text="Готово", callback_data="int:done")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def place_actions_kb(place_id: str, route_url: str, phone: str | None, site: str | None) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text="Маршрут", callback_data=f"act:route:place:{place_id}")]]
    if phone:
        buttons[0].append(InlineKeyboardButton(text="Позвонить", callback_data=f"act:call:place:{place_id}"))
    if site:
        buttons[0].append(InlineKeyboardButton(text="Сайт", callback_data=f"act:site:place:{place_id}"))
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def event_actions_kb(event_id: str, route_url: str, site: str | None) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text="Маршрут", callback_data=f"act:route:event:{event_id}")]]
    if site:
        buttons[0].append(InlineKeyboardButton(text="Сайт", callback_data=f"act:site:event:{event_id}"))
    buttons[0].append(InlineKeyboardButton(text="Забронировать", callback_data=f"act:book:event:{event_id}"))
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def event_actions_kb_with_gallery(event_id: str, route_url: str, site: str | None) -> InlineKeyboardMarkup:
    base = event_actions_kb(event_id, route_url, site)
    rows = list(base.inline_keyboard or [])
    rows.append([
        InlineKeyboardButton(text="⟨ Фото", callback_data=f"img:prev:event:{event_id}"),
        InlineKeyboardButton(text="Фото ⟩", callback_data=f"img:next:event:{event_id}"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_menu_kb() -> ReplyKeyboardMarkup:
    food_label = rc.get("bot_menu_food_label", "🍴 Где поесть")
    events_label = rc.get("bot_menu_events_label", "🎤 Куда сходить")
    poll_label = rc.get("bot_menu_poll_label", "🗳 Опрос")
    ugc_label = rc.get("bot_menu_ugc_label", "➕ Добавить событие")
    rows = [
        [KeyboardButton(text=food_label), KeyboardButton(text=events_label)],
        [KeyboardButton(text=poll_label), KeyboardButton(text=ugc_label)],
        [KeyboardButton(text="Сменить город")],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


# Helpers with a Back button to main menu
def place_actions_kb_with_back(place_id: str, route_url: str, phone: str | None, site: str | None) -> InlineKeyboardMarkup:
    base = place_actions_kb(place_id, route_url, phone, site)
    rows = list(base.inline_keyboard or [])
    rows.append([InlineKeyboardButton(text="Назад", callback_data="nav:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def event_actions_kb_with_back(event_id: str, route_url: str, site: str | None) -> InlineKeyboardMarkup:
    base = event_actions_kb(event_id, route_url, site)
    rows = list(base.inline_keyboard or [])
    rows.append([InlineKeyboardButton(text="Назад", callback_data="nav:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
