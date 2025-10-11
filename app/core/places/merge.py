from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from app.core.places.types import PlaceRecord
from app.core.services.geo import distance_km


def _norm_name(name: str) -> str:
    return " ".join(name.lower().split())


def merge_places(records: Iterable[PlaceRecord], threshold_m: float = 50.0) -> list[PlaceRecord]:
    """Merge duplicate places by name and proximity.

    - Same normalized name
    - Distance <= threshold_m (50 meters by default)
    - Prefer best attributes: higher rating, existing phone/hours/price_level
    """

    groups: dict[str, list[PlaceRecord]] = defaultdict(list)
    for r in records:
        groups[_norm_name(r.name)].append(r)

    merged: list[PlaceRecord] = []
    for name, items in groups.items():
        clusters: list[list[PlaceRecord]] = []
        for it in items:
            placed = False
            for cluster in clusters:
                # Compare with first item in cluster
                ref = cluster[0]
                if distance_km(it.lat, it.lon, ref.lat, ref.lon) * 1000.0 <= threshold_m:
                    cluster.append(it)
                    placed = True
                    break
            if not placed:
                clusters.append([it])

        for cluster in clusters:
            best = cluster[0]
            for it in cluster[1:]:
                # Prefer higher rating
                if (it.rating or 0.0) > (best.rating or 0.0):
                    best = it
            # Combine attributes
            phone = next((x.phone for x in cluster if x.phone), best.phone)
            hours = next((x.hours for x in cluster if x.hours), best.hours)
            price_level = next((x.price_level for x in cluster if x.price_level is not None), best.price_level)
            rating = max([x.rating or 0.0 for x in cluster]) or best.rating

            merged.append(
                PlaceRecord(
                    id=best.id,
                    name=best.name,
                    category=best.category,
                    address=best.address or next((x.address for x in cluster if x.address), ""),
                    lat=best.lat,
                    lon=best.lon,
                    phone=phone,
                    hours=hours,
                    rating=rating if rating is not None else None,
                    price_level=price_level,
                    source=best.source,
                    external_id=best.external_id,
                )
            )

    return merged

