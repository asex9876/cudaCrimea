from __future__ import annotations

from app.core.places.merge import merge_places
from app.core.places.types import PlaceRecord


def test_merge_duplicates_by_distance_and_name() -> None:
    a = PlaceRecord(
        name="Кафе Ромашка",
        category="cafe",
        address="ул. Ленина, 1",
        lat=44.952100,
        lon=34.102400,
        phone=None,
        hours=None,
        rating=4.3,
        price_level=2,
        source="2gis",
        external_id="a1",
    )
    b = PlaceRecord(
        name="кафе  ромашка",
        category="cafe",
        address="Ленина 1",
        lat=44.952101,  # ~0.1m away
        lon=34.102401,
        phone="+7 999 000-00-00",
        hours={"always_open": True},
        rating=4.7,
        price_level=None,
        source="yandex",
        external_id="b1",
    )

    merged = merge_places([a, b], threshold_m=50.0)
    assert len(merged) == 1
    m = merged[0]
    assert m.name.lower().startswith("кафе")
    # Rating should be max
    assert m.rating == 4.7
    # Phone/hours should be taken from available record
    assert m.phone == "+7 999 000-00-00"
    assert m.hours is not None

