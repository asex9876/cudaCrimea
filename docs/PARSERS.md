# 📡 Система парсинга событий

## Обзор

Автоматическая система сбора событий из различных источников с использованием парсеров, API и AI-экстракции.

---

## 🎯 Источники данных

### 1. **KudaGo API** (Рекомендуется) ⭐

**Файл:** `app/ingestors/kudago.py`

**Описание:**
Официальный API агрегатора событий KudaGo. Самый надёжный источник с структурированными данными.

**Что извлекается:**
- ✅ Название, дата, время
- ✅ Место проведения с координатами
- ✅ Категория события
- ✅ Описание (полное)
- ✅ Цена (мин/макс)
- ✅ Фотографии (высокого качества)
- ✅ Ссылка на источник

**Города:** Севастополь, Симферополь, Ялта, Евпатория, Феодосия

**Частота:** Каждые 6 часов (настраивается)

**Преимущества:**
- Не требует браузер (простой HTTP)
- Официальный API без блокировок
- Структурированные данные
- Высокое качество информации
- Фотографии высокого разрешения

**Настройки в админке:**
```python
ingest_kudago_enabled = True  # Включить/выключить
ingest_kudago_hours = 6  # Частота парсинга (часы)
ingest_kudago_cities = ["Севастополь", "Симферополь", "Ялта"]
```

---

### 2. **Yandex Афиша**

**Файл:** `app/ingestors/yandex_afisha.py`

**Описание:**
Парсинг Яндекс.Афиша с использованием Playwright (браузер).

**Что извлекается:**
- ✅ Название, дата, время
- ✅ Место проведения
- ✅ Цена
- ❌ Координаты (часто отсутствуют)
- ❌ Подробное описание

**Города:** Севастополь, Симферополь

**Частота:** Каждые 4 часа

**Особенности:**
- Требует Playwright (браузерный движок)
- Может быть нестабильным при изменении вёрстки
- Медленнее чем API

---

### 3. **Afisha Goroda (Город Севастополь/Симферополь)**

**Файл:** `app/ingestors/afisha_goroda.py`

**Описание:**
Парсинг локальных сайтов gorodsevastopol.ru и gorod-simferopol.ru

**Что извлекается:**
- ✅ Название, дата
- ✅ Место проведения
- ✅ Цена
- ⚠️ Время (иногда отсутствует)

**Города:** Севастополь, Симферополь

**Частота:** Каждые 4 часа

**Особенности:**
- Локальные события
- Может дублировать другие источники

---

### 4. **Afisha82.ru** 🎪 (Крым)

**Файл:** `app/ingestors/afisha82_ru.py`

**Описание:**
Главный портал событий Крыма. Парсинг всех категорий событий с автоматическим извлечением контактов.

**Что извлекается:**
- ✅ Название, дата начала и окончания
- ✅ Место проведения
- ✅ Цена (автоматическое определение)
- ✅ Изображения
- ✅ Контакты: телефон, email, Telegram, VK, Instagram
- ✅ Полное описание

**Технология:** BeautifulSoup + HTTP

**Особенности:**
- Поддержка долгоиграющих событий (фестивали)
- Автоматическое извлечение дат окончания
- Парсинг русских дат
- Отправка в очередь модерации (не напрямую в БД)

**Запуск вручную:**
```bash
docker exec cuda_api python -m app.ingestors.afisha82_ru
```

**Лимиты:** 50 событий за запуск, 0.3 сек между запросами

---

### 5. **Kassa24 Севастополь** 🎟️ (Крым)

**Файл:** `app/ingestors/sevastopol_kassa24.py`

**Описание:**
Билетная платформа Севастополя. Парсинг всех категорий развлечений и культурных событий.

**Категории:**
- Театр (66+ событий)
- Концерты (17+)
- Экскурсии (15+)
- Кино (10+)
- Спорт, выставки

**Что извлекается:**
- ✅ Название, дата, время
- ✅ Место проведения
- ✅ Цена (точная с сайта билетов)
- ✅ Изображения
- ✅ Контакты организаторов
- ✅ Описание

**Технология:** BeautifulSoup + HTTP

**Особенности:**
- Точные цены (билетная платформа)
- События требующие билеты
- Проверенные организаторы

**Запуск вручную:**
```bash
docker exec cuda_api python -m app.ingestors.sevastopol_kassa24
```

---

### 6. **Culture.ru** 🏛️ (Крым)

**Файл:** `app/ingestors/culture_ru.py`

**Описание:**
Портал Министерства культуры РФ. Официальные культурные события во всех городах Крыма.

**Города:**
- Севастополь
- Симферополь
- Ялта
- Феодосия
- Евпатория

**Что извлекается:**
- ✅ Название, дата
- ✅ Место проведения
- ✅ Цена (большинство бесплатны)
- ✅ Изображения
- ✅ Контакты
- ✅ JSON-LD structured data

**Технология:** BeautifulSoup + HTTP + JSON-LD

**Особенности:**
- Официальные государственные мероприятия
- Большинство событий бесплатны
- Музеи, библиотеки, культурные центры
- Поддержка structured data

**Запуск вручную:**
```bash
docker exec cuda_api python -m app.ingestors.culture_ru
```

---

### 7. **Afisha.ru Севастополь** 📰 (Крым)

**Файл:** `app/ingestors/afisha_ru_sevastopol.py`

**Описание:**
Крупнейший событийный портал России (секция Севастополь).

**Категории:**
- Концерты
- Театр
- Выставки
- Фестивали
- Шоу

**Что извлекается:**
- ✅ Название, дата
- ✅ Место проведения
- ✅ Цена
- ✅ Изображения
- ✅ Контакты
- ✅ JSON-LD + OpenGraph

**Технология:** BeautifulSoup + HTTP + structured data

**Особенности:**
- Крупные события
- Популярные площадки
- Профессиональная фотография
- Автоматическое определение типа события

**Запуск вручную:**
```bash
docker exec cuda_api python -m app.ingestors.afisha_ru_sevastopol
```

---

### 8. **Telegram каналы + AI экстракция** 🤖

**Файлы:**
- `app/ingestors/tg_channels.py` - сбор постов
- `app/ingestors/tg_ai_extractor.py` - AI экстракция

**Описание:**
Собирает посты из Telegram каналов и использует AI для извлечения информации о событиях.

**Как работает:**
1. Telethon собирает посты из указанных каналов
2. AI (GPT-4o-mini) анализирует текст поста
3. Извлекает: название, дату, время, место, цену, категорию
4. Классифицирует категорию события
5. Отправляет в очередь модерации

**Настройка Telegram:**
```env
# .env
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
TELEGRAM_SESSION=your_session_string
TG_CHANNELS=@CrimeaEvents,@SevastopolNews
```

**Настройка AI:**
```env
AI_MEDIATOR_API_KEY=your_key
AI_MEDIATOR_BASE_URL=https://api.ai-mediator.ru/v1
OPENAI_MODEL_EXTRACTOR=gpt-4o-mini
OPENAI_MODEL_CLASSIFIER=gpt-4o-mini
```

**Преимущества:**
- Находит уникальные события
- Автоматическая категоризация
- Извлечение из неструктурированного текста

**Недостатки:**
- Требует API ключ для AI
- Может быть неточным
- Медленнее других парсеров

---

## 📞 Модуль извлечения контактов

**Файл:** `app/ingestors/contact_extractor.py`

Все крымские парсеры используют этот модуль для автоматического извлечения контактной информации.

**Поддерживаемые типы контактов:**
- 📞 Телефон (российские форматы: +7, 8)
- 📧 Email
- 📱 Telegram username
- 🔵 VK ссылки
- 📷 Instagram username

**Функции:**

```python
extract_phone(text: str) -> Optional[str]
# +7 (978) 123-45-67, 8 (978) 123-45-67

extract_email(text: str) -> Optional[str]
# info@example.ru

extract_telegram(text: str) -> Optional[str]
# @username → username (без @)

extract_vk(text: str) -> Optional[str]
# https://vk.com/group

extract_instagram(text: str) -> Optional[str]
# @username → username

extract_all_contacts(text: str) -> dict
# Все контакты одновременно

format_contacts_for_display(contacts: dict) -> str
# Форматирование с эмодзи
```

**Пример использования:**
```python
from app.ingestors.contact_extractor import extract_all_contacts

text = "Справки по телефону +7 (978) 123-45-67 или @event_organizer"
contacts = extract_all_contacts(text)
# {
#   "phone": "+7 (978) 123-45-67",
#   "telegram": "event_organizer",
#   "email": None,
#   "vk": None,
#   "instagram": None
# }
```

---

## 🔄 Система очередей и модерации

### Три типа очередей

**Redis очереди:**
- `ugc:queue` - Бесплатные события от пользователей
- `ugc:queue:paid` - Платные события от пользователей
- `ugc:queue:parser` - События от парсеров

### Визуальное отличие в админке

**Рамки карточек событий:**
- 🟦 Серая рамка - бесплатные события
- 🟥 Красная рамка - платные события
- 🟨 **Желтая рамка (#FFD700) - парсенные события**

**Бейджи:**
- 🤖 Парсер: afisha82
- 🤖 Парсер: kassa24
- 🤖 Парсер: culture.ru
- 🤖 Парсер: afisha.ru

### Фильтры в очереди

**URL:** `/admin/ugc?queue={filter}`

**Доступные фильтры:**
- `all` - Все события (по умолчанию)
- `free` - Только бесплатные от пользователей
- `paid` - Только платные от пользователей
- `parser` - Только парсенные события

### Workflow парсера

```
1. Парсер собирает события →
2. Извлекает контакты →
3. Формирует payload →
4. Добавляет в ugc:queue:parser →
5. Админ видит в очереди с желтой рамкой →
6. Approve → Событие в БД →
7. Reject → Удалено из очереди
```

### Структура payload в очереди

```json
{
  "form": {
    "title": "Название события",
    "date_iso": "2025-10-15T19:00:00",
    "venue": "Место проведения",
    "description": "Описание",
    "phone": "+7 (978) 123-45-67",
    "email": "info@example.ru",
    "telegram": "username",
    "vk": "https://vk.com/group",
    "instagram": "username",
    "price": "500",
    "is_free": false
  },
  "raw_text": "Полный текст для LLM",
  "source": "parser",
  "parser_name": "afisha82",
  "wants_paid_promotion": false,
  "images": ["https://example.com/image.jpg"]
}
```

---

## ⚙️ Настройка парсеров

### Через админ-панель

**URL:** `/admin/parsers`

1. Перейдите в админку: `http://localhost/admin/`
2. Раздел "Парсеры"
3. Выберите парсер для запуска
4. Нажмите "▶️ Запустить"
5. Проверьте результат в очереди `/admin/ugc?queue=parser`

### Ручной запуск парсера

**Кнопка "Запустить"** в админ-панели:
```http
POST /admin/parsers/run/{parser_name}
Content-Type: application/x-www-form-urlencoded

csrf={csrf_token}
```

**Доступные парсеры:**
- `kudago` - KudaGo API
- `yandex` - Яндекс.Афиша (требует Playwright)
- `goroda` - Afisha-Goroda.ru
- `afisha82` - ✅ Afisha82.ru (Крым)
- `kassa24` - ✅ Kassa24 Севастополь (Крым)
- `culture` - ✅ Culture.ru (Крым)
- `afisha_ru` - ✅ Afisha.ru Севастополь (Крым)
- `tg` - Telegram + AI

### Запуск всех активных парсеров

**Кнопка "Запустить все"** в админ-панели:
```http
POST /admin/parsers/run-all
```

### Через старые настройки (устарело)

1. Раздел "Настройки парсеров" (старая версия)
2. Включите/выключите нужные источники
3. Настройте частоту парсинга
4. Выберите города для каждого парсера

### Через переменные окружения (.env)

```bash
# KudaGo (рекомендуется)
ingest_kudago_enabled=true
ingest_kudago_hours=6
ingest_kudago_cities=["Севастополь", "Симферополь", "Ялта"]

# Yandex Афиша
ingest_yandex_enabled=true
ingest_yandex_hours=4
ingest_yandex_cities=["Севастополь", "Симферополь"]

# Афиша Города
ingest_goroda_enabled=true
ingest_goroda_hours=4
ingest_goroda_cities=["Севастополь", "Симферополь"]

# Telegram
ingest_tg_enabled=true
ingest_tg_minutes=45
```

---

## 🔄 Как работает автоматический парсинг

### Worker (фоновый процесс)

**Файл:** `app/ingestors/worker.py`

**Процесс:**
1. APScheduler запускает задачи по расписанию
2. Каждый парсер запускается для каждого города отдельно
3. События сохраняются в БД через `upsert_event()`
4. Дедупликация по названию + дата + место
5. Логирование результатов

**Пример работы:**
```
09:00 - KudaGo Севастополь (найдено 45 событий)
09:10 - KudaGo Симферополь (найдено 38 событий)
13:00 - Yandex Севастополь (найдено 22 события)
13:15 - Telegram каналы (найдено 5 событий)
```

---

## 📊 Дедупликация

### Как работает

**Файл:** `app/ingestors/normalize.py`

**Алгоритм:**
1. Нормализация названия (lowercase, trim)
2. Fuzzy matching названий (90% сходство)
3. Проверка совпадения даты
4. Проверка совпадения места (90% сходство)

**Пример:**
```
"Концерт в ДК" + 2025-01-15 + "ДК Севастополь"
vs
"Концерт  в  ДК " + 2025-01-15 + "ДК Севастополя"
→ Считается дубликатом ✅
```

---

## 🧪 Тестирование парсеров

### Запуск вручную

```bash
# KudaGo
docker exec cuda_worker python -c "
import asyncio
from app.ingestors.kudago import ingest
from app.db.session import get_sessionmaker

async def test():
    ss = get_sessionmaker()
    async with ss() as session:
        count = await ingest('Севастополь', session)
        print(f'Imported {count} events')

asyncio.run(test())
"

# Yandex
docker exec cuda_worker python -c "
import asyncio
from app.ingestors.yandex_afisha import ingest
from app.db.session import get_sessionmaker

async def test():
    ss = get_sessionmaker()
    async with ss() as session:
        count = await ingest('Севастополь', session)
        print(f'Imported {count} events')

asyncio.run(test())
"

# Telegram AI экстракция
cd app/ingestors
python tg_ai_extractor.py  # Запустит тестовый пример
```

---

## 📈 Мониторинг

### Логи парсеров

```bash
# Смотреть логи worker
docker logs cuda_worker -f

# Фильтровать по источнику
docker logs cuda_worker 2>&1 | grep "kudago"
docker logs cuda_worker 2>&1 | grep "yandex"
docker logs cuda_worker 2>&1 | grep "tg_ai"
```

### Метрики

```bash
# Статистика по источникам
docker exec cuda_db psql -U postgres cudacrimea -c "
SELECT source, COUNT(*) as count, MAX(created_at) as last_updated
FROM events
GROUP BY source
ORDER BY count DESC;
"

# События за последние 24 часа
docker exec cuda_db psql -U postgres cudacrimea -c "
SELECT source, COUNT(*) as count
FROM events
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY source;
"
```

---

## 🚀 Добавление нового парсера

### Шаблон парсера

```python
# app/ingestors/my_source.py
"""My new event source parser."""

from __future__ import annotations
import structlog
from app.db.dao.events import upsert_event
from app.core.services.quality import source_weight

logger = structlog.get_logger(module="ing.my_source")


async def fetch_events(city: str) -> list[dict]:
    """Fetch events from source."""
    # Ваша логика парсинга
    return [
        {
            "title": "Событие",
            "date": "2025-01-15",
            "time": "19:00",
            "venue_name": "Место",
            # ...
        }
    ]


async def ingest(city: str, session) -> int:
    """Import events to database."""
    events = await fetch_events(city)
    imported = 0

    for event in events:
        await upsert_event(
            session,
            title=event["title"],
            date_=event["date"],
            city=city,
            source="my_source",
            quality_base=source_weight("my_source"),
            # ...
        )
        imported += 1

    logger.info("my_source.complete", city=city, count=imported)
    return imported
```

### Регистрация в worker

```python
# app/ingestors/worker.py
from app.ingestors import my_source

async def job_my_source(city: str):
    ss = get_sessionmaker()
    async with ss() as session:
        await my_source.ingest(city, session)

# В _schedule_jobs():
if rc.get("ingest_my_source_enabled", True):
    scheduler.add_job(
        job_my_source,
        IntervalTrigger(hours=4),
        id="my_source",
        args=["Севастополь"],
    )
```

---

## 💡 Рекомендации

### Оптимальная конфигурация

Для **максимального покрытия событий**:
```python
ingest_kudago_enabled = True  # ОСНОВНОЙ источник
ingest_yandex_enabled = True  # Дополнительный
ingest_goroda_enabled = False # Много дубликатов
ingest_tg_enabled = True  # Уникальные события

ingest_kudago_hours = 6  # Достаточно часто
ingest_yandex_hours = 8  # Реже (дублирует KudaGo)
ingest_tg_minutes = 60  # Часто (новые посты)
```

### Для экономии ресурсов

```python
ingest_kudago_enabled = True  # Только KudaGo
ingest_yandex_enabled = False
ingest_goroda_enabled = False
ingest_tg_enabled = False  # Требует AI API

ingest_kudago_hours = 12  # Реже
```

---

## 🔧 Troubleshooting

### Парсер не работает

1. Проверьте логи: `docker logs cuda_worker -f`
2. Проверьте настройки в админке
3. Проверьте переменные окружения (.env)
4. Убедитесь что worker запущен: `docker ps | grep cuda_worker`

### Много дубликатов

1. Проверьте качество дедупликации в `normalize.py`
2. Уменьшите количество активных парсеров
3. Используйте только KudaGo (наименьшее количество дубликатов)

### AI экстракция не работает

1. Проверьте API ключ: `AI_MEDIATOR_API_KEY` в .env
2. Проверьте логи: `docker logs cuda_worker 2>&1 | grep "tg_ai"`
3. Проверьте лимиты API (AI Mediator/OpenAI)

---

## 📞 Поддержка

При проблемах с парсерами проверьте:
1. Логи worker: `docker logs cuda_worker -f`
2. Статус БД: `docker ps | grep cuda_db`
3. Настройки в админке: `/admin/settings`
4. Документацию API источников
