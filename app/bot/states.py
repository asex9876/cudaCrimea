from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class StartStates(StatesGroup):
    choosing_city = State()


class NearbyFoodStates(StatesGroup):
    waiting_location = State()


class WhatToDoStates(StatesGroup):
    choosing_when = State()
    entering_budget = State()
    choosing_interests = State()
    showing_results = State()


class UGCStates(StatesGroup):
    entering_text = State()
    confirming = State()
    adding_photos = State()


class UGCFormStates(StatesGroup):
    choosing_mode = State()
    entering_title = State()
    entering_date = State()
    entering_time = State()
    choosing_city = State()
    entering_address = State()
    waiting_location = State()
    entering_price_min = State()
    entering_price_max = State()
    choosing_category = State()
    entering_link = State()
    adding_photos = State()
    confirming = State()
    choosing_paid_promotion = State()


class PaidPlacementStates(StatesGroup):
    """States for paid placement flow with monetization."""
    choosing_type = State()
    entering_zone = State()
    confirming = State()
