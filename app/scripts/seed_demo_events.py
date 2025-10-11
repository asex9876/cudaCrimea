from __future__ import annotations

import asyncio
from datetime import date, timedelta, time
from typing import Sequence

from sqlalchemy import insert

from app.core.logging import setup_logging
from app.db.models.tables import Event
from app.db.session import get_sessionmaker


CATEGORIES: Sequence[str] = ("concert", "theatre", "kids", "tour", "party", "expo", "other")


def _samples_for_city(city: str) -> list[dict]:
    today = date.today()
    samples: list[dict] = []
    base_lat_lon = {
        "Севастополь": (44.6167, 33.5254),
        "Симферополь": (44.9521, 34.1024),
    }
    blat, blon = base_lat_lon.get(city, (44.6167, 33.5254))
    for cat in CATEGORIES:
        for i in range(5):
            d = today + timedelta(days=i % 5)
            samples.append(
                {
                    "title": f"Демо {cat} #{i+1} ({city})",
                    "date": d,
                    "time": time(hour=18 + (i % 3) * 2, minute=0),
                    "price_min": 300 + i * 100,
                    "price_max": 1000 + i * 200,
                    "category": cat,
                    "venue_name": f"Площадка {i+1}",
                    "address": f"{city}, Центральная {i+1}",
                    "lat": blat + (i * 0.001),
                    "lon": blon + (i * 0.001),
                    "source": "seed",
                    "source_url": "https://example.com/demo",
                    "quality_score": 0.6,
                    "image_url": None,
                }
            )
    return samples


async def main() -> None:
    setup_logging()
    ss = get_sessionmaker()
    async with ss() as session:  # type: ignore[call-arg]
        for city in ("Севастополь", "Симферополь"):
            rows = _samples_for_city(city)
            await session.execute(insert(Event).values(rows))
        await session.commit()
    print("Seeded demo events for categories.")


if __name__ == "__main__":
    asyncio.run(main())

