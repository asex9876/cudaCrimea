# AI-Based Parsing System Migration

## Обзор

Все парсеры событий теперь используют **единую AI-based систему извлечения данных** вместо ручного парсинга по "ключевым точкам" (HTML-селекторам и регулярным выражениям).

## Архитектура

### Компоненты системы

1. **`app/ingestors/ai_parser_base.py`** - Базовый модуль для AI-парсинга
   - `parse_event_with_ai()` - Парсит событие из текста (2-этапный процесс)
   - `enqueue_parsed_event()` - Добавляет событие в очередь модерации
   - Использует Redis для кеширования результатов (TTL 24 часа)

2. **`app/core/llm/is_event_classifier.py`** - Классификатор
   - Определяет, является ли текст событием
   - Использует промпт из БД (LLMPrompt) или дефолтный

3. **`app/core/llm/extractor.py`** - Экстрактор данных
   - Извлекает структурированные поля события
   - Возвращает валидированную модель `EventDraft`
   - Использует промпт из БД или дефолтный

4. **`app/core/llm/client.py`** - LLM клиент
   - Работает с AI Mediator API или OpenAI
   - Логирует использование токенов в `LLMUsage`

### Двухэтапный процесс парсинга

```
Текст события → [1. Классификатор] → Это событие?
                         ↓ Да
               [2. Экстрактор] → Структурированные данные
                         ↓
               [Валидация] → EventDraft
                         ↓
               [Кеширование] → Redis
                         ↓
               [Очередь модерации] → ugc:queue:parser
```

## Мигрированные парсеры

### ✅ Полностью мигрированы

1. **KudaGo** (`kudago.py`)
   - API-парсер
   - Преобразует JSON в текст для AI
   - Сохраняет координаты и изображения из API

2. **Yandex Afisha** (`yandex_afisha.py`)
   - HTML-парсер через Playwright
   - Извлекает карточки событий целиком
   - AI анализирует текст карточки

3. **Afisha Goroda** (`afisha_goroda.py`)
   - HTML-парсер
   - Использует `ingest_generic_html_site()`

4. **Kassa24** (`kassa24.py`)
   - HTML-парсер
   - Использует `ingest_generic_html_site()`

### ℹ️ Частично мигрированы

5. **Telegram Channels** (`tg_channels.py` + `tg_ai_extractor.py`)
   - Уже использовал AI через `tg_ai_extractor.py`
   - Теперь использует единые промпты из базы данных
   - Работает через UGC-очередь

### ⚠️ Требуют миграции

Следующие парсеры нужно мигрировать по образцу выше:

- `afisha_ru_sevastopol.py`
- `afisha82_ru.py`
- `culture_ru.py`
- `sevastopol_kassa24.py`

**Инструкция по миграции:**

```python
# 1. Добавить импорты
from app.ingestors.migrate_html_parsers import ingest_generic_html_site

# 2. В функции ingest() заменить логику на:
async def ingest(city: str, session) -> int:
    # Fetch HTML (оставить как есть)
    html = await fetch_html(city)

    # Использовать AI-парсинг
    queued = await ingest_generic_html_site(
        html=html,
        city=city,
        parser_name="parser_name_here",
        base_url="https://site.ru",
        card_selectors=["article", ".event-card", ".afisha-item"],
    )

    return queued
```

## Преимущества новой системы

### 1. Точность
- AI понимает контекст, а не полагается на жесткие селекторы
- Извлекает данные даже если HTML-разметка изменилась
- Автоматически определяет категории событий

### 2. Универсальность
- Один подход для всех источников (API, HTML, Telegram, будущие)
- Не требует поддержки селекторов для каждого сайта
- Легко добавлять новые источники

### 3. Производительность
- Redis-кеш для повторяющегося контента (TTL 24ч)
- Избегает повторных вызовов AI для одинаковых постов
- Логирование использования токенов

### 4. Гибкость
- Промпты хранятся в БД (`LLMPrompt`)
- Можно обновлять без изменения кода
- Поддержка A/B тестирования промптов

### 5. Качество данных
- Автоматическое извлечение контактов (phone, email, telegram, vk, instagram)
- Нормализация дат и времени
- Категоризация событий

## Конфигурация

### Переменные окружения

```bash
# AI Mediator (или OpenAI)
AI_MEDIATOR_BASE_URL=https://api.ai-mediator.ru/v1
AI_MEDIATOR_API_KEY=your_key_here

# Модели
OPENAI_MODEL_CLASSIFIER=gpt-4o-mini  # Классификатор
OPENAI_MODEL_EXTRACTOR=gpt-4o-mini   # Экстрактор

# Auth headers (если нужно)
LLM_AUTH_HEADER=Authorization
LLM_AUTH_SCHEME=Bearer
```

### Промпты в БД

Таблица: `llm_prompts`

```sql
SELECT * FROM llm_prompts WHERE is_active = true;
```

Типы промптов:
- `classifier` - для определения событий
- `extractor` - для извлечения полей

## Мониторинг

### Логи

```bash
# Успешный парсинг
ai_parser.success source_type=kudago_api title="Концерт" date=2025-10-20

# Не событие
ai_parser.not_event source_type=telegram reasons=["Это реклама, а не событие"]

# Ошибка
ai_parser.error source_type=yandex_afisha error="..." text_preview="..."
```

### Использование токенов

```sql
SELECT
    service,
    model,
    SUM(total_tokens) as total_tokens,
    COUNT(*) as requests,
    AVG(total_tokens) as avg_tokens_per_request
FROM llm_usage
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY service, model;
```

### Кеш-метрики

```bash
# Redis stats
docker exec cuda_redis redis-cli INFO stats | grep keyspace_hits
docker exec cuda_redis redis-cli KEYS "ai_parse:*" | wc -l
```

## Тестирование

### Ручной тест парсера

```python
from app.ingestors.ai_parser_base import parse_event_with_ai
import asyncio

async def test():
    result = await parse_event_with_ai(
        text="""
        Концерт группы "Крым-Рок"
        15 декабря 2025 в 19:00
        ДК Севастополь, ул. Ленина 10
        Билеты: 500-1000₽
        """,
        source_url="https://example.com/event/123",
        source_type="test",
        city="Севастополь",
        use_cache=False,
    )
    print(result)

asyncio.run(test())
```

### Проверка промптов

```python
from app.core.llm.is_event_classifier import get_active_classifier_prompt
from app.core.llm.extractor import get_active_extractor_prompt
import asyncio

async def show_prompts():
    classifier = await get_active_classifier_prompt()
    extractor = await get_active_extractor_prompt()
    print("=== CLASSIFIER ===")
    print(classifier)
    print("\n=== EXTRACTOR ===")
    print(extractor)

asyncio.run(show_prompts())
```

## Troubleshooting

### Проблема: AI не распознает событие

**Решение:**
1. Проверить промпт классификатора в БД
2. Проверить логи: `ai_parser.not_event`
3. Обновить промпт через админ-панель

### Проблема: Неправильные данные

**Решение:**
1. Проверить промпт экстрактора
2. Проверить валидацию `EventDraft`
3. Добавить примеры в промпт

### Проблема: Низкая производительность

**Решение:**
1. Проверить кеш-хиты в Redis
2. Уменьшить частоту парсинга в `worker.py`
3. Использовать более быстрые модели

### Проблема: Превышен лимит токенов

**Решение:**
1. Ограничить длину входного текста (сейчас: 3000 символов)
2. Использовать модели с большим context window
3. Проверить запросы в `llm_usage`

## Roadmap

- [ ] Мигрировать оставшиеся парсеры
- [ ] A/B тестирование промптов
- [ ] Автоматическая оптимизация промптов
- [ ] Fallback на ручной парсинг при ошибках AI
- [ ] Batch-обработка для экономии токенов
- [ ] Поддержка multimodal (изображения + текст)

## Контакты

При вопросах по AI-парсингу:
- Проверьте логи: `app.ingestors.ai_parser`
- Проверьте конфигурацию промптов в админ-панели
- Проверьте статистику в таблице `llm_usage`
