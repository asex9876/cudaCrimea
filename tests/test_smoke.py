from __future__ import annotations

from app.api.main import app
from app.core.config import get_settings


def test_settings_loaded() -> None:
    s = get_settings()
    assert s.app_name


def test_api_app_exists() -> None:
    assert app is not None

