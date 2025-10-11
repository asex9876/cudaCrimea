from __future__ import annotations

from typing import Any, Optional

import httpx
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential_jitter

from app.core.config import get_settings
from app.core.places.types import PlaceRecord


_CAT_MAP = {
    "кафе": "cafe",
    "бар": "bar",
    "ресторан": "restaurant",
    "кофе": "coffee",
}


def _spn_from_radius(lat: float, radius_m: int) -> tuple[float, float]:
    # Roughly convert meters to degrees
    dlat = radius_m / 111_000.0
    from math import cos, pi

    dlon = radius_m / (111_000.0 * max(0.1, abs(cos(lat * pi / 180.0))))
    return dlon * 2, dlat * 2  # span width,height


async def search_places(
    *,
    category: str,
    lat: float,
    lon: float,
    radius_m: int,
    open_now: bool = False,
    limit: int = 50,
) -> list[PlaceRecord]:
    s = get_settings()
    apikey = s.yandex_maps_api_key
    if not apikey:
        return []

    url = s.yandex_maps_search_url
    spn_w, spn_h = _spn_from_radius(lat, radius_m)
    params = {
        "text": category,
        "type": "biz",
        "ll": f"{lon},{lat}",
        "spn": f"{spn_w:.6f},{spn_h:.6f}",
        "lang": "ru_RU",
        "results": min(int(limit), 50),
        "apikey": apikey,
    }
    timeout = httpx.Timeout(10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        data: dict[str, Any] | None = None
        async for _ in AsyncRetrying(stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=1, max=5)):
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        if data is None:
            return []

    results: list[PlaceRecord] = []
    for feat in data.get("features", []):
        geom = feat.get("geometry", {})
        coords = geom.get("coordinates") or []
        if len(coords) != 2:
            continue
        lonv, latv = float(coords[0]), float(coords[1])
        props = feat.get("properties", {})
        meta = props.get("CompanyMetaData", {})
        name = meta.get("name") or props.get("name") or ""
        address = meta.get("address") or props.get("description") or ""
        phone = None
        for p in meta.get("Phones", []) or []:
            if p.get("type") == "phone" or p.get("formatted"):
                phone = p.get("formatted") or p.get("number")
                break
        hours = meta.get("Hours") or None
        cat = _CAT_MAP.get(category.lower(), "other")
        results.append(
            PlaceRecord(
                id=None,
                name=name,
                category=cat,
                address=address,
                lat=latv,
                lon=lonv,
                phone=phone,
                hours=hours,
                rating=None,
                price_level=None,
                source="yandex",
                external_id=str(feat.get("id")),
            )
        )

    # open_now filter best-effort (if Hours has 'is_open_now' flag; not always present)
    if open_now:
        results = [r for r in results if not r.hours or r.hours.get("is_open_now", True)]

    return results

