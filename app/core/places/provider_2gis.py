from __future__ import annotations

from typing import Any, Optional

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from app.core.config import get_settings
from app.core.places.types import PlaceRecord


_CAT_MAP = {
    "кафе": "cafe",
    "бар": "bar",
    "ресторан": "restaurant",
    "кофе": "coffee",
}


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
    api_key = s.two_gis_api_key

    if not api_key:
        return []

    url = "https://catalog.api.2gis.com/3.0/items"
    params = {
        "q": category,
        "point": f"{lon},{lat}",
        "radius": int(radius_m),
        "page_size": min(int(limit), 50),
        "fields": "items.geometry,items.contact_groups,items.schedule,items.rubrics,items.address_name,items.full_address_name",
        "key": api_key,
    }

    timeout = httpx.Timeout(10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        data: dict[str, Any] | None = None
        async for attempt in AsyncRetrying(stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=1, max=5)):
            with attempt:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
        if data is None:
            return []

    results: list[PlaceRecord] = []
    for it in data.get("result", {}).get("items", []):
        geom = (it.get("geometry") or {}).get("centroid") or (it.get("geometry") or {}).get("location")
        if not geom:
            continue
        latv = float(geom.get("lat"))
        lonv = float(geom.get("lon"))
        # Phones
        phone = None
        for cg in it.get("contact_groups", []) or []:
            for c in cg.get("contacts", []) or []:
                if c.get("type") == "phone":
                    phone = c.get("value")
                    break
            if phone:
                break
        # Hours
        schedule = it.get("schedule") or {}
        hours = None
        if schedule:
            hours = {"round_the_clock": schedule.get("is_round_the_clock")}
        name = it.get("name") or ""
        address = it.get("full_address_name") or it.get("address_name") or ""
        rubrics = [r.get("name", "").lower() for r in it.get("rubrics", []) or []]
        # Map category to canonical
        cat = _CAT_MAP.get(category.lower(), "other")
        if not cat and rubrics:
            for ru in rubrics:
                for k, v in _CAT_MAP.items():
                    if k in ru:
                        cat = v
                        break
        results.append(
            PlaceRecord(
                id=None,
                name=name,
                category=cat or "other",
                address=address,
                lat=latv,
                lon=lonv,
                phone=phone,
                hours=hours,
                rating=None,
                price_level=None,
                source="2gis",
                external_id=str(it.get("id")),
            )
        )

    # Filter open_now if possible
    if open_now:
        filtered: list[PlaceRecord] = []
        for r in results:
            if r.hours and r.hours.get("round_the_clock"):
                filtered.append(r)
            else:
                # If schedule unknown, keep; rely on ranking to penalize later
                filtered.append(r)
        results = filtered

    return results
