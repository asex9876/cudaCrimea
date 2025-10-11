"""Geospatial helpers and deeplink builders.

Functions include Haversine distance, coordinate normalization, and
deeplink generators for Yandex.Maps and 2GIS.
"""

from __future__ import annotations

import math
import urllib.parse
from typing import Tuple

from haversine import Unit, haversine


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute Haversine distance in kilometers.

    Args:
        lat1: Latitude of point A.
        lon1: Longitude of point A.
        lat2: Latitude of point B.
        lon2: Longitude of point B.

    Returns:
        Distance in kilometers.
    """

    return float(haversine((lat1, lon1), (lat2, lon2), unit=Unit.KILOMETERS))


def normalize_coords(lat: float, lon: float) -> tuple[float, float]:
    """Normalize latitude and longitude to valid ranges.

    Args:
        lat: Latitude, may overflow [-90, 90].
        lon: Longitude, may overflow [-180, 180].

    Returns:
        Tuple of normalized `(lat, lon)`.
    """

    # Clamp latitude to [-90, 90]
    lat = max(-90.0, min(90.0, lat))
    # Wrap longitude to [-180, 180]
    lon = ((lon + 180.0) % 360.0) - 180.0
    return lat, lon


def yandex_deeplink(lat: float, lon: float, label: str | None = None) -> str:
    """Build a Yandex.Maps deeplink URL.

    Args:
        lat: Latitude.
        lon: Longitude.
        label: Optional label/search text.

    Returns:
        URL string pointing to Yandex.Maps with a marker.
    """

    lat, lon = normalize_coords(lat, lon)
    params = {
        "pt": f"{lon:.6f},{lat:.6f}",
        "z": "17",
        "l": "map",
    }
    if label:
        params["text"] = label
    return "https://yandex.ru/maps/?" + urllib.parse.urlencode(params)


def two_gis_deeplink(lat: float, lon: float, label: str | None = None) -> str:
    """Build a 2GIS deeplink URL.

    Args:
        lat: Latitude.
        lon: Longitude.
        label: Optional label.

    Returns:
        URL string pointing to 2GIS.
    """

    lat, lon = normalize_coords(lat, lon)
    # Route to point variant; 2GIS expects lon,lat
    base = f"https://2gis.ru/routeSearch/to/{lon:.6f},{lat:.6f}"
    if label:
        base += "?m=15&query=" + urllib.parse.quote(label)
    return base

