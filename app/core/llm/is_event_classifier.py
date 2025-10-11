"""Binary classifier to determine if text describes an event."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.llm import client as llm_client


class ClassifierOut(BaseModel):
    is_event: bool = False
    reasons: list[str] = Field(default_factory=list)


SYS_PROMPT = (
    "Ты классификатор. Ответь JSON {is_event: boolean, reasons: string[]}. "
    "is_event=true только если текст описывает конкретное событие / мероприятие (дата, место, афиша). "
    "Не добавляй ничего кроме JSON."
)


def classify(text: str) -> ClassifierOut:
    s = get_settings()
    model = s.openai_model_classifier
    content = llm_client.chat_complete(model=model, messages=[{"role": "system", "content": SYS_PROMPT}, {"role": "user", "content": text}], temperature=0.0)
    data = json.loads(content)
    return ClassifierOut.model_validate(data)
