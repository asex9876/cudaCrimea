"""Ranking functions for events and places.

Composite score:
    score = w1*time_recency + w2*geo_proximity + w3*interest_match
             + w4*source_quality + w5*popularity [+ w6*is_open]

Weights are read from environment via `Settings` (see app.core.config).
All components are normalized to [0, 1].
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time as dtime
from typing import Any, Mapping, Optional

from app.core.config import get_settings
from app.core import runtime_config as rc
from app.core.services.geo import distance_km
from app.core.services.interests import event_match, place_match
from app.core.services.quality import combined_quality


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """Get attribute or mapping key with fallback.

    Args:
        obj: Source object or mapping.
        key: Attribute/key name.
        default: Fallback value.

    Returns:
        Value from obj.
    """

    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _recency_score(ev_date: date, ev_time: Optional[dtime], now: datetime) -> float:
    # Build naive event datetime for comparison
    ev_dt = datetime.combine(ev_date, ev_time or dtime(hour=12))
    days = (ev_dt.date() - now.date()).days
    if days < 0:
        return 0.0
    # Linear decay over 30 days
    return _clamp01(1.0 - (days / 30.0))


def _proximity_score(user_lat: Optional[float], user_lon: Optional[float], lat: Optional[float], lon: Optional[float]) -> float:
    if user_lat is None or user_lon is None or lat is None or lon is None:
        return 0.0
    d = distance_km(user_lat, user_lon, lat, lon)
    # Linear decay to 0 at 50 km
    return _clamp01(1.0 - min(d, 50.0) / 50.0)


def _popularity_event(value: Optional[float]) -> float:
    if value is None:
        return 0.0
    v = float(value)
    # If value is [0,1], keep; if >1, scale by 100
    return _clamp01(v if v <= 1.0 else v / 100.0)


def _popularity_place(rating: Optional[float]) -> float:
    if rating is None:
        return 0.0
    return _clamp01(float(rating) / 5.0)


def _is_open(hours: Any) -> float:
    # Simplified: respect explicit always_open flag if present
    if isinstance(hours, Mapping):
        v = hours.get("always_open")
        if isinstance(v, bool):
            return 1.0 if v else 0.0
    # unknown schedule → neutral 0.5
    return 0.5


def score_event(user_ctx: Mapping[str, Any], event: Any, now: datetime) -> float:
    """Compute event ranking score.

    Args:
        user_ctx: Mapping with user context (expects keys: `home_lat`, `home_lon`, `prefs`).
        event: ORM or mapping with fields used by the scorer.
        now: Current datetime.

    Returns:
        Score in [0, 1].
    """

    s = get_settings()

    ev_date: date = _get(event, "date")
    ev_time: Optional[dtime] = _get(event, "time")
    lat: Optional[float] = _get(event, "lat")
    lon: Optional[float] = _get(event, "lon")
    category: str = _get(event, "category")
    price_min: Optional[int] = _get(event, "price_min")
    price_max: Optional[int] = _get(event, "price_max")
    source: Optional[str] = _get(event, "source")
    quality_score: Optional[float] = _get(event, "quality_score")
    popularity_raw: Optional[float] = _get(event, "popularity")

    time_recency = _recency_score(ev_date, ev_time, now)
    geo_proximity = _proximity_score(user_ctx.get("home_lat"), user_ctx.get("home_lon"), lat, lon)
    interest = event_match(user_ctx.get("prefs", {}), category, price_min, price_max)
    source_q = combined_quality(source, quality_score)
    popularity = _popularity_event(popularity_raw)

    w_time = float(rc.get("w_time", s.w_time))
    w_geo = float(rc.get("w_geo", s.w_geo))
    w_interest = float(rc.get("w_interest", s.w_interest))
    w_source = float(rc.get("w_source", s.w_source))
    w_pop = float(rc.get("w_pop", s.w_pop))
    score = w_time * time_recency + w_geo * geo_proximity + w_interest * interest + w_source * source_q + w_pop * popularity
    return _clamp01(score)


def score_place(user_ctx: Mapping[str, Any], place: Any, now: datetime) -> float:
    """Compute place ranking score.

    Args:
        user_ctx: Mapping with user context (expects `home_lat`, `home_lon`, `prefs`).
        place: ORM or mapping with fields used by the scorer.
        now: Current datetime (unused except for possible hours logic extensions).

    Returns:
        Score in [0, 1].
    """

    s = get_settings()

    lat: Optional[float] = _get(place, "lat")
    lon: Optional[float] = _get(place, "lon")
    category: str = _get(place, "category")
    price_level: Optional[int] = _get(place, "price_level")
    rating: Optional[float] = _get(place, "rating")
    source: Optional[str] = _get(place, "source")
    quality_score: Optional[float] = _get(place, "quality_score")
    hours = _get(place, "hours")

    geo_proximity = _proximity_score(user_ctx.get("home_lat"), user_ctx.get("home_lon"), lat, lon)
    interest = place_match(user_ctx.get("prefs", {}), category, price_level, rating)
    source_q = combined_quality(source, quality_score)
    popularity = _popularity_place(rating)
    open_score = _is_open(hours)

    w_geo = float(rc.get("w_geo", s.w_geo))
    w_interest = float(rc.get("w_interest", s.w_interest))
    w_source = float(rc.get("w_source", s.w_source))
    w_pop = float(rc.get("w_pop", s.w_pop))
    w_open = float(rc.get("w_open", s.w_open))
    score = w_geo * geo_proximity + w_interest * interest + w_source * source_q + w_pop * popularity + w_open * open_score
    return _clamp01(score)
