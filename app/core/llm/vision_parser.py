"""Vision parser for extracting event data from posters and flyers using GPT-4 Vision.

Processes images (posters, flyers, screenshots) to extract structured event information.
"""

from __future__ import annotations

import json
from typing import Any, Optional

import structlog
from openai import OpenAI

from app.core.config import get_settings
from app.core.llm.extractor import EventDraft

logger = structlog.get_logger(module="vision_parser")


VISION_SYSTEM_PROMPT = """Ты — эксперт по извлечению информации о событиях из афиш и постеров.

Проанализируй изображение и извлеки всю доступную информацию о событии в формате JSON:

{
  "title": "название события",
  "date_iso": "YYYY-MM-DD",
  "time_24h": "HH:MM или null",
  "venue_name": "название места проведения",
  "address": "адрес",
  "price_min": число или null,
  "price_max": число или null,
  "category": "concert|theatre|kids|tour|party|expo|other|sport",
  "age_restriction": "0+|6+|12+|16+|18+ или null",
  "organizer": "организатор или имя артиста",
  "end_time": "HH:MM или null",
  "duration_minutes": число или null,
  "capacity": число или null,
  "ticket_type": "sale|booking|free|registration или null"
}

ВАЖНО:
- Извлекай только то, что явно указано на изображении
- Если информации нет - ставь null
- Не придумывай данные
- Даты могут быть в формате "15 января", "15.01", "15 Jan" - преобразуй в YYYY-MM-DD
- Цены могут быть с символами валюты - извлекай только числа
- Возрастные ограничения ищи как "6+", "12+", "18+" и т.д.
- Если на афише несколько событий - извлеки главное/основное
"""


class VisionParser:
    """Parser for extracting event data from images using GPT-4 Vision."""

    def __init__(self):
        """Initialize vision parser with OpenAI client."""
        settings = get_settings()

        # Use AI Mediator if configured, otherwise use OpenAI
        if settings.ai_mediator_base_url and settings.ai_mediator_api_key:
            self.client = OpenAI(
                base_url=settings.ai_mediator_base_url,
                api_key=settings.ai_mediator_api_key,
            )
            self.model = "gpt-4-vision-preview"  # Check if AI Mediator supports vision
            logger.info("vision_parser.using_ai_mediator")
        elif settings.openai_api_key:
            self.client = OpenAI(
                base_url=settings.openai_base_url,
                api_key=settings.openai_api_key,
            )
            self.model = "gpt-4-vision-preview"
            logger.info("vision_parser.using_openai")
        else:
            raise ValueError("No vision API configured (need AI Mediator or OpenAI)")

    def parse_image(
        self,
        image_url: str,
        detail: str = "high",
    ) -> EventDraft | None:
        """Parse event information from image URL.

        Args:
            image_url: URL of the image to parse (must be publicly accessible).
            detail: Image detail level ("low", "high", "auto"). High uses more tokens but better accuracy.

        Returns:
            EventDraft | None: Extracted event data or None if parsing failed.
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": VISION_SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Извлеки информацию о событии из этого изображения:",
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": image_url,
                                    "detail": detail,
                                },
                            },
                        ],
                    },
                ],
                max_tokens=1000,
                temperature=0.0,
            )

            content = response.choices[0].message.content
            if not content:
                logger.warning("vision_parser.empty_response", image_url=image_url)
                return None

            # Extract JSON from response
            try:
                # Try to parse as JSON directly
                data = json.loads(content)
            except json.JSONDecodeError:
                # Extract JSON substring
                start = content.find("{")
                end = content.rfind("}")
                if start != -1 and end != -1 and end > start:
                    data = json.loads(content[start : end + 1])
                else:
                    logger.warning(
                        "vision_parser.json_parse_failed",
                        image_url=image_url,
                        response=content[:200],
                    )
                    return None

            # Validate and convert to EventDraft
            draft = EventDraft.model_validate(data)

            logger.info(
                "vision_parser.success",
                image_url=image_url,
                title=draft.title,
                category=draft.category,
            )

            return draft

        except Exception as e:
            logger.error(
                "vision_parser.parse_failed",
                image_url=image_url,
                error=str(e),
            )
            return None

    def parse_image_base64(
        self,
        image_base64: str,
        detail: str = "high",
    ) -> EventDraft | None:
        """Parse event information from base64-encoded image.

        Args:
            image_base64: Base64-encoded image string (data:image/jpeg;base64,... format).
            detail: Image detail level ("low", "high", "auto").

        Returns:
            EventDraft | None: Extracted event data or None if parsing failed.
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": VISION_SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Извлеки информацию о событии из этого изображения:",
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": image_base64,
                                    "detail": detail,
                                },
                            },
                        ],
                    },
                ],
                max_tokens=1000,
                temperature=0.0,
            )

            content = response.choices[0].message.content
            if not content:
                logger.warning("vision_parser.empty_response")
                return None

            # Extract JSON from response
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                start = content.find("{")
                end = content.rfind("}")
                if start != -1 and end != -1 and end > start:
                    data = json.loads(content[start : end + 1])
                else:
                    logger.warning(
                        "vision_parser.json_parse_failed",
                        response=content[:200],
                    )
                    return None

            draft = EventDraft.model_validate(data)

            logger.info(
                "vision_parser.success_base64",
                title=draft.title,
                category=draft.category,
            )

            return draft

        except Exception as e:
            logger.error(
                "vision_parser.parse_base64_failed",
                error=str(e),
            )
            return None


# Singleton instance
_vision_parser: VisionParser | None = None


def get_vision_parser() -> VisionParser:
    """Get singleton vision parser instance.

    Returns:
        VisionParser: Shared parser instance.
    """
    global _vision_parser
    if _vision_parser is None:
        _vision_parser = VisionParser()
    return _vision_parser
