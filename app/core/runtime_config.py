from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import structlog


logger = structlog.get_logger(module="runtime_config")

_OVERRIDES: dict[str, Any] = {}
_FILE_PATH = Path(__file__).resolve().parent / "data" / "settings.json"


def get(key: str, default: Any | None = None) -> Any | None:
    return _OVERRIDES.get(key, default)


def set_many(values: Mapping[str, Any]) -> None:
    _OVERRIDES.update(values)
    logger.info("runtime_config.updated", keys=list(values.keys()))


def all_overrides() -> dict[str, Any]:
    return dict(_OVERRIDES)


def load_from_file(path: Path | None = None) -> None:
    p = path or _FILE_PATH
    if not p.exists():
        return
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            set_many(data)
            logger.info("runtime_config.loaded", path=str(p))
    except Exception as e:  # noqa: BLE001
        logger.warning("runtime_config.load_failed", error=str(e))


def save_to_file(path: Path | None = None) -> None:
    p = path or _FILE_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(_OVERRIDES, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("runtime_config.saved", path=str(p))

