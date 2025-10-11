"""Seed base Crimea cities into a local reference file.

This script writes a JSON file under `app/core/data/cities.json` containing
a basic list of Crimean cities for use in dropdowns or defaults.
"""

from __future__ import annotations

import json
from pathlib import Path

import structlog

from app.core.logging import setup_logging


DATA_DIR = Path(__file__).resolve().parents[1] / "core" / "data"
DATA_FILE = DATA_DIR / "cities.json"

logger = structlog.get_logger(module="scripts.seed_cities")


DEFAULT_CITIES = [
    "Симферополь",
    "Севастополь",
    "Ялта",
    "Евпатория",
    "Феодосия",
    "Керчь",
    "Алушта",
    "Судак",
    "Бахчисарай",
    "Саки",
    "Алупка",
    "Гурзуф",
    "Коктебель",
    "Щёлкино",
]


def main() -> None:
    setup_logging()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with DATA_FILE.open("w", encoding="utf-8") as f:
        json.dump({"cities": DEFAULT_CITIES}, f, ensure_ascii=False, indent=2)
    logger.info("seed.cities.written", path=str(DATA_FILE), count=len(DEFAULT_CITIES))


if __name__ == "__main__":
    main()

