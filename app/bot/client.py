from __future__ import annotations

import json
from typing import Any, Optional

import httpx
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential_jitter

from app.core.config import get_settings


TIMEOUT = httpx.Timeout(5.0)


async def api_search(params: dict[str, Any]) -> dict[str, Any]:
    s = get_settings()
    url = f"http://{s.api_host}:{s.api_port}/api/search"
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        # Drop None/empty params to avoid 422 (e.g., budget_max=None)
        q = {k: v for k, v in params.items() if v is not None and v != ""}
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential_jitter(initial=0.5, max=2),
        ):
            with attempt:
                resp = await client.get(url, params=q)
                resp.raise_for_status()
                return resp.json()


async def api_poll_create(payload: dict[str, Any]) -> dict[str, Any]:
    s = get_settings()
    url = f"http://{s.api_host}:{s.api_port}/api/poll/create"
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential_jitter(initial=0.5, max=2),
        ):
            with attempt:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                return resp.json()


async def api_ugc_submit(payload: dict[str, Any]) -> dict[str, Any]:
    s = get_settings()
    url = f"http://{s.api_host}:{s.api_port}/api/ugc/submit"
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential_jitter(initial=0.5, max=2),
        ):
            with attempt:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                return resp.json()
