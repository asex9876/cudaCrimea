"""Binary classifier to determine if text describes an event."""

from __future__ import annotations

import json
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.llm import client as llm_client


class ClassifierOut(BaseModel):
    is_event: bool = False
    reasons: list[str] = Field(default_factory=list)


# Default fallback prompt
DEFAULT_SYS_PROMPT = (
    "Ты классификатор. Ответь JSON {is_event: boolean, reasons: string[]}. "
    "is_event=true только если текст описывает конкретное событие / мероприятие (дата, место, афиша). "
    "Не добавляй ничего кроме JSON."
)


async def get_active_classifier_prompt() -> str:
    """Get active classifier prompt from database or return default."""
    try:
        from app.db.session import get_sessionmaker
        from app.db.models import LLMPrompt
        from sqlalchemy import select

        async_session_maker = get_sessionmaker()
        async with async_session_maker() as session:
            result = await session.execute(
                select(LLMPrompt)
                .where(LLMPrompt.prompt_type == 'classifier')
                .where(LLMPrompt.is_active == True)
            )
            prompt = result.scalar_one_or_none()
            return prompt.system_prompt if prompt else DEFAULT_SYS_PROMPT
    except Exception:
        return DEFAULT_SYS_PROMPT


def classify(text: str, custom_prompt: Optional[str] = None) -> ClassifierOut:
    """Classify text as event or not. Uses custom_prompt if provided, otherwise uses default."""
    s = get_settings()
    model = s.openai_model_classifier

    # Use custom prompt if provided, otherwise use default
    sys_prompt = custom_prompt if custom_prompt is not None else DEFAULT_SYS_PROMPT

    content = llm_client.chat_complete(
        model=model,
        messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": text}],
        temperature=0.0,
        service="classifier"
    )
    data = json.loads(content)
    return ClassifierOut.model_validate(data)
