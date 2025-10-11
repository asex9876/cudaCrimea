"""Telegram channels ingestor using Telethon."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Iterable, Optional

import structlog
from redis import asyncio as aioredis
from telethon import TelegramClient
from telethon.sessions import StringSession

from app.core.config import get_settings
from app.core.logging import setup_logging


logger = structlog.get_logger(module="ing.tg")


async def fetch_posts(limit: int = 50) -> list[dict[str, Any]]:
    s = get_settings()
    if not (s.tg_api_id and s.tg_api_hash and s.tg_session):
        logger.warning("tg.missing_credentials")
        return []

    client = TelegramClient(StringSession(s.tg_session), s.tg_api_id, s.tg_api_hash)
    await client.connect()
    posts: list[dict[str, Any]] = []
    try:
        for ch in s.tg_channels:
            try:
                entity = await client.get_entity(ch)
            except Exception as e:  # noqa: BLE001
                logger.warning("tg.channel.resolve_failed", channel=ch, error=str(e))
                continue
            async for msg in client.iter_messages(entity, limit=limit):
                media_url = None
                if msg.media and msg.file and msg.file.name:
                    media_url = f"tg://{msg.file.name}"
                posts.append(
                    {
                        "channel": ch,
                        "ts": msg.date.isoformat() if msg.date else datetime.utcnow().isoformat(),
                        "text": msg.message or "",
                        "media_url": media_url,
                    }
                )
    finally:
        await client.disconnect()
    return posts


async def enqueue_posts(posts: Iterable[dict[str, Any]]) -> int:
    s = get_settings()
    redis = aioredis.from_url(str(s.redis_url), decode_responses=True)
    cnt = 0
    async with redis.client() as r:
        for p in posts:
            await r.lpush("ugc:raw", json.dumps(p, ensure_ascii=False))
            cnt += 1
    await redis.aclose()
    logger.info("tg.enqueued", count=cnt)
    return cnt

