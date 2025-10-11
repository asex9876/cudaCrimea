from __future__ import annotations

from datetime import datetime, timedelta
import os

import pytest

from app.core.config import get_settings
from app.core.services.ranking import score_event, score_place


USER = {"home_lat": 44.9521, "home_lon": 34.1024, "prefs": {"event_categories": ["concert"], "place_categories": ["cafe"], "budget_max": 1000, "price_level_max": 3}}


def test_event_recency() -> None:
    now = datetime(2025, 1, 1, 12, 0)
    ev_soon = {"date": now.date(), "time": None, "category": "concert", "source": "afisha", "source_url": "", "lat": 44.95, "lon": 34.1}
    ev_late = {"date": (now + timedelta(days=25)).date(), "time": None, "category": "concert", "source": "afisha", "source_url": "", "lat": 44.95, "lon": 34.1}
    s1 = score_event(USER, ev_soon, now)
    s2 = score_event(USER, ev_late, now)
    assert s1 > s2


def test_event_geo_proximity() -> None:
    now = datetime(2025, 1, 1, 12, 0)
    near = {"date": now.date(), "time": None, "category": "concert", "source": "afisha", "source_url": "", "lat": USER["home_lat"], "lon": USER["home_lon"]}
    far = {"date": now.date(), "time": None, "category": "concert", "source": "afisha", "source_url": "", "lat": 45.5, "lon": 37.5}
    s_near = score_event(USER, near, now)
    s_far = score_event(USER, far, now)
    assert s_near > s_far


def test_event_interest_match() -> None:
    now = datetime(2025, 1, 1, 12, 0)
    like = {"date": now.date(), "time": None, "category": "concert", "source": "afisha", "source_url": ""}
    dislike = {"date": now.date(), "time": None, "category": "expo", "source": "afisha", "source_url": ""}
    s_like = score_event(USER, like, now)
    s_dislike = score_event(USER, dislike, now)
    assert s_like > s_dislike


def test_event_source_quality() -> None:
    now = datetime(2025, 1, 1, 12, 0)
    good = {"date": now.date(), "time": None, "category": "concert", "source": "afisha", "source_url": ""}
    bad = {"date": now.date(), "time": None, "category": "concert", "source": "unknown", "source_url": ""}
    s_good = score_event(USER, good, now)
    s_bad = score_event(USER, bad, now)
    assert s_good > s_bad


def test_place_popularity_rating() -> None:
    now = datetime(2025, 1, 1, 12, 0)
    top = {"category": "cafe", "lat": USER["home_lat"], "lon": USER["home_lon"], "rating": 5.0, "source": "2gis", "hours": {"always_open": True}}
    low = {"category": "cafe", "lat": USER["home_lat"], "lon": USER["home_lon"], "rating": 2.0, "source": "2gis", "hours": {"always_open": True}}
    s_top = score_place(USER, top, now)
    s_low = score_place(USER, low, now)
    assert s_top > s_low


def test_place_is_open_weight(monkeypatch: pytest.MonkeyPatch) -> None:
    # Enable W_OPEN for this test
    monkeypatch.setenv("W_OPEN", "0.1")
    get_settings.cache_clear()  # reload settings with env override
    now = datetime(2025, 1, 1, 12, 0)
    opened = {"category": "cafe", "lat": USER["home_lat"], "lon": USER["home_lon"], "rating": 4.0, "source": "2gis", "hours": {"always_open": True}}
    closed = {"category": "cafe", "lat": USER["home_lat"], "lon": USER["home_lon"], "rating": 4.0, "source": "2gis", "hours": {"always_open": False}}
    s_open = score_place(USER, opened, now)
    s_closed = score_place(USER, closed, now)
    assert s_open > s_closed
    # Cleanup cache for other tests
    monkeypatch.delenv("W_OPEN", raising=False)
    get_settings.cache_clear()

