"""Telegram channels ingestor using Telethon with AI extraction."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Iterable, Optional

import structlog
from redis import asyncio as aioredis
from telethon import TelegramClient
from telethon.sessions import StringSession
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.models import UGCSubmission
from app.db.session import get_sessionmaker


logger = structlog.get_logger(module="ing.tg")


# AI Prompt for Telegram event extraction
TELEGRAM_PARSER_PROMPT = """Извлеки информацию о событии из этого Telegram поста.

ВАЖНО:
- Если в тексте НЕТ информации о событии (концерт, выставка, спектакль и т.д.), верни пустой JSON: {}
- Если есть событие, извлеки все доступные данные
- Для дат: если указан только день недели или "сегодня/завтра", используй текущую дату контекста
- Для многодневных событий: заполни end_date если указан период (например "с 15 по 20 января")
- Цены: извлеки минимальную и максимимальную, или только одну если цена фиксированная

Формат ответа (JSON):
{
  "title": "Название события",
  "description": "Подробное описание",
  "date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD или null для однодневных событий",
  "time": "HH:MM или null",
  "end_time": "HH:MM или null",
  "venue_name": "Название места проведения",
  "address": "Адрес",
  "city": "Город",
  "price_min": число или null,
  "price_max": число или null,
  "category": "concert/theater/exhibition/sport/education/kids/party/festival/cinema/other",
  "age_restriction": "0+/6+/12+/16+/18+ или null",
  "organizer": "Имя организатора или null",
  "contacts": "Телефон/email/соцсети"
}

Текущая дата для контекста: {current_date}

Telegram пост:
{text}"""


# Lazy imports for AI
def _get_llm_client():
    from app.core.llm import client as llm_client
    return llm_client


def _get_geocoding_service():
    from app.core.services.geocoding import GeocodingService
    return GeocodingService


def _get_embedding_service():
    from app.core.services.embedding import get_embedding_service
    return get_embedding_service()


def _get_validator():
    from app.core.services.validation import get_validation_service
    return get_validation_service()


async def extract_event_from_telegram_post(
    text: str,
    channel: str,
    post_url: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Извлечь структурированные данные о событии из Telegram поста используя AI.

    Args:
        text: Текст поста
        channel: Имя канала
        post_url: URL поста (опционально)

    Returns:
        Словарь с данными события или None если событие не найдено
    """
    if not text or len(text.strip()) < 20:
        logger.debug("tg.extract.text_too_short", channel=channel)
        return None

    llm_client = _get_llm_client()

    # Форматируем prompt с текущей датой
    current_date = datetime.now().strftime("%Y-%m-%d")
    prompt = TELEGRAM_PARSER_PROMPT.format(
        current_date=current_date,
        text=text
    )

    # Логируем первые 300 символов текста поста для отладки
    # Заменяем {} на [] чтобы избежать проблем с форматированием
    safe_preview = text[:300].replace("{", "[").replace("}", "]")
    logger.info("tg.extract.processing_post", channel=channel, text_preview=safe_preview, text_length=len(text))

    try:
        response = await llm_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ты - эксперт по извлечению информации о событиях. Отвечай только валидным JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            response_format={"type": "json_object"}
        )

        raw_json = response.choices[0].message.content
        if not raw_json:
            logger.warning("tg.extract.empty_response", channel=channel)
            return None

        # Логируем сырой ответ от AI для отладки (заменяем {} чтобы избежать ошибок форматирования)
        safe_response = raw_json[:500].replace("{", "[").replace("}", "]")
        logger.info("tg.extract.ai_raw_response", channel=channel, response=safe_response)

        extracted = json.loads(raw_json)

        # Если пустой JSON - событие не найдено
        if not extracted or not extracted.get("title"):
            # Сериализуем в JSON строку чтобы избежать проблем с форматированием
            logger.info("tg.extract.no_event", channel=channel, extracted_data=json.dumps(extracted) if extracted else "{}")
            return None

        # Заменяем {} в title чтобы избежать ошибок форматирования
        safe_title = (extracted.get("title") or "").replace("{", "[").replace("}", "]")
        logger.info("tg.extract.success", channel=channel, title=safe_title)
        return extracted

    except Exception as e:
        logger.error("tg.extract.failed", channel=channel, error=str(e))
        return None


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

                # Формируем URL поста
                post_url = None
                if hasattr(entity, 'username') and entity.username:
                    post_url = f"https://t.me/{entity.username}/{msg.id}"

                posts.append(
                    {
                        "channel": ch,
                        "ts": msg.date.isoformat() if msg.date else datetime.utcnow().isoformat(),
                        "text": msg.message or "",
                        "media_url": media_url,
                        "post_url": post_url,
                    }
                )
    finally:
        await client.disconnect()
    return posts


async def process_and_save_posts(
    posts: Iterable[dict[str, Any]],
    session: AsyncSession
) -> int:
    """Обработать Telegram посты с AI извлечением и сохранить в UGC очередь.

    Args:
        posts: Список постов из fetch_posts()
        session: Асинхронная сессия БД

    Returns:
        Количество успешно обработанных событий
    """
    GeocodingService = _get_geocoding_service()
    geocoding_service = GeocodingService(session)
    embedding_service = _get_embedding_service()
    validator = _get_validator()

    saved_count = 0

    for post in posts:
        try:
            # Извлекаем событие из текста поста
            extracted = await extract_event_from_telegram_post(
                text=post.get("text", ""),
                channel=post.get("channel", "unknown"),
                post_url=post.get("post_url")
            )

            if not extracted:
                continue

            # Валидация данных
            try:
                validated_data = validator.validate_event(extracted)
            except Exception as e:
                logger.warning("tg.validation_failed", channel=post.get("channel"), error=str(e))
                validated_data = extracted

            # Геокодинг адреса
            lat, lon = None, None
            address = validated_data.get("address")
            city = validated_data.get("city", "Севастополь")

            if address:
                try:
                    coords = await geocoding_service.geocode_address(address, city)
                    if coords:
                        lat, lon = coords
                except Exception as e:
                    logger.warning("tg.geocoding_failed", address=address, error=str(e))

            # Формируем extracted_data для UGC
            extracted_data = {
                "title": validated_data.get("title"),
                "description": validated_data.get("description"),
                "date": validated_data.get("date"),
                "end_date": validated_data.get("end_date"),
                "time": validated_data.get("time"),
                "end_time": validated_data.get("end_time"),
                "city": city,
                "venue_name": validated_data.get("venue_name", "Не указано"),
                "address": address or "",
                "lat": lat,
                "lon": lon,
                "price_min": validated_data.get("price_min"),
                "price_max": validated_data.get("price_max"),
                "category": validated_data.get("category", "other"),
                "age_restriction": validated_data.get("age_restriction"),
                "organizer": validated_data.get("organizer"),
                "contacts": validated_data.get("contacts"),
                "source": f"telegram:{post.get('channel')}",
                "source_url": post.get("post_url"),
            }

            # Генерация embedding
            embedding_vector = None
            try:
                embedding_vector = embedding_service.generate_event_embedding(
                    title=validated_data.get("title", ""),
                    date=str(validated_data.get("date", "")),
                    venue=validated_data.get("venue_name", ""),
                    description=validated_data.get("description"),
                )
            except Exception as e:
                logger.warning("tg.embedding_failed", error=str(e))

            if embedding_vector:
                extracted_data["embedding"] = embedding_vector

            # Создаем UGC submission
            ugc_submission = UGCSubmission(
                id=uuid.uuid4(),
                user_id=0,  # Системный пользователь для парсеров
                raw_text=post.get("text", ""),
                source_url=post.get("post_url"),
                extracted_data=extracted_data,
                is_ai_structured=True,
                parser_source="telegram",
                status="parsed",  # Готово к модерации
            )

            session.add(ugc_submission)
            saved_count += 1

            # Заменяем {} в title чтобы избежать ошибок форматирования
            safe_title = (validated_data.get("title") or "").replace("{", "[").replace("}", "]")
            logger.info(
                "tg.event_saved",
                channel=post.get("channel"),
                title=safe_title,
            )

        except Exception as e:
            logger.error(
                "tg.process_failed",
                channel=post.get("channel"),
                error=str(e)
            )
            continue

    # Коммит всех событий
    if saved_count > 0:
        try:
            await session.commit()
            logger.info("tg.batch_saved", count=saved_count)
        except Exception as e:
            logger.error("tg.commit_failed", error=str(e))
            await session.rollback()
            saved_count = 0

    return saved_count

