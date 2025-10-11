"""Short event/venue summarizer without emojis."""

from __future__ import annotations

from app.core.config import get_settings
from app.core.llm import client as llm_client


SYS_PROMPT = (
    "Суммаризируй текст короткой карточкой: 1–2 предложения, без эмодзи, без маркетинговых клише."
)


def summarize(text: str) -> str:
    s = get_settings()
    model = s.openai_model_summarizer
    content = llm_client.chat_complete(
        model=model,
        messages=[{"role": "system", "content": SYS_PROMPT}, {"role": "user", "content": text}],
        temperature=0.2,
        max_tokens=120,
    )
    # Ensure no emojis (strip most common ranges)
    filtered = "".join(ch for ch in content if not (0x1F300 <= ord(ch) <= 0x1FAFF))
    return filtered.strip()
