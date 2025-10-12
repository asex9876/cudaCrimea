from __future__ import annotations

from typing import Any, Optional
import uuid

import httpx

from app.core.config import get_settings


def chat_complete(*, model: str, messages: list[dict[str, str]], temperature: float = 0.0, max_tokens: int | None = None, service: Optional[str] = None) -> str:
    """Call an OpenAI-compatible /chat/completions endpoint and return text content.

    Uses AI Mediator when configured via env, otherwise falls back to OPENAI_* envs.
    Auth header name and scheme are configurable (default: Authorization: Bearer <key>).
    """

    s = get_settings()
    from app.core import runtime_config as rc

    base_url = (
        (rc.get("ai_mediator_base_url") or s.ai_mediator_base_url or s.openai_base_url or "").rstrip("/")
        or "https://api.ai-mediator.ru/v1"
    )
    api_key = (rc.get("ai_mediator_api_key") or s.ai_mediator_api_key or s.openai_api_key or "")
    if not api_key:
        raise RuntimeError("LLM API key is not configured (AI_MEDIATOR_API_KEY or OPENAI_API_KEY)")

    url = f"{base_url}/chat/completions"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    auth_header = (rc.get("llm_auth_header") or s.llm_auth_header or "Authorization")
    auth_scheme = (rc.get("llm_auth_scheme") or s.llm_auth_scheme or "Bearer").strip()
    auth_value = f"{auth_scheme} {api_key}" if auth_header.lower() == "authorization" else api_key
    headers[auth_header] = auth_value

    payload: dict[str, Any] = {"model": model, "messages": messages, "temperature": float(temperature)}
    if max_tokens is not None:
        payload["max_tokens"] = int(max_tokens)

    with httpx.Client(timeout=30.0) as client:
        resp = client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    # OpenAI-compatible shape
    try:
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"Invalid LLM response: {data}") from e

    # Log token usage asynchronously (fire and forget)
    if service and usage:
        try:
            _log_llm_usage_async(
                service=service,
                model=model,
                provider="ai-mediator" if "ai-mediator" in base_url else "openai",
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            )
        except Exception:  # noqa: BLE001
            pass  # Don't fail the request if logging fails

    return content or ""


def _log_llm_usage_async(*, service: str, model: str, provider: str, prompt_tokens: int, completion_tokens: int, total_tokens: int) -> None:
    """Log LLM usage to database (fire and forget)."""
    import asyncio
    from app.db.session import get_sessionmaker
    from app.db.models import LLMUsage

    async def _log():
        async_session_maker = get_sessionmaker()
        async with async_session_maker() as session:
            usage = LLMUsage(
                id=uuid.uuid4(),
                service=service,
                model=model,
                provider=provider,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
            )
            session.add(usage)
            await session.commit()

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(_log())
        else:
            asyncio.run(_log())
    except Exception:  # noqa: BLE001
        pass  # Silent failure
