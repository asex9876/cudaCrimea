from __future__ import annotations

from app.core.services.geo import two_gis_deeplink, yandex_deeplink


def deeplink_yandex(lat: float, lon: float, label: str | None = None) -> str:
    return yandex_deeplink(lat, lon, label)


def deeplink_2gis(lat: float, lon: float, label: str | None = None) -> str:
    return two_gis_deeplink(lat, lon, label)

