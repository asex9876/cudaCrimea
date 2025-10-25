# AI CONTEXT - Справочник для языковых моделей

> **ВАЖНО**: Этот файл предназначен для языковых моделей (Claude, GPT и др.) для быстрого восстановления контекста проекта cudaCrimea. Содержит критически важную информацию об архитектуре, частых ошибках и особенностях разработки.

---

## 📋 ОГЛАВЛЕНИЕ

1. [О проекте](#о-проекте)
2. [Архитектура и инфраструктура](#архитектура-и-инфраструктура)
3. [Критические особенности](#критические-особенности)
4. [Частые ошибки и решения](#частые-ошибки-и-решения)
5. [Структура базы данных](#структура-базы-данных)
6. [Системы парсинга](#системы-парсинга)
7. [Админ-панель](#админ-панель)
8. [Деплой и обслуживание](#деплой-и-обслуживание)
9. [Чеклист для новой сессии](#чеклист-для-новой-сессии)

---

## О ПРОЕКТЕ

**cudaCrimea** - платформа для агрегации и модерации событий в Крыму.

### Основные компоненты:
- **FastAPI Backend** (app/admin/main.py) - админ-панель и API
- **PostgreSQL** - основная БД (события, пользователи, подписки)
- **Redis** - кеш, очереди, runtime-конфиг
- **APScheduler Worker** - фоновые задачи парсинга
- **Telegram Parser** - парсинг из Telegram-каналов (Telethon)
- **Universal Parser** - AI-парсинг любых веб-сайтов (OpenAI)

### Технологии:
- Python 3.11+
- FastAPI + Uvicorn
- SQLAlchemy 2.0 (async)
- Alembic (миграции)
- Redis (aioredis)
- Telethon (Telegram Client)
- OpenAI API (GPT-4 для извлечения событий)
- BeautifulSoup4 (парсинг HTML)

---

## АРХИТЕКТУРА И ИНФРАСТРУКТУРА

### Docker-контейнеры на сервере:

```
5.83.140.80 (root)
├── cuda_api      - FastAPI приложение (порт 8000)
├── cuda_worker   - APScheduler фоновые задачи
├── cuda_db       - PostgreSQL 15
└── cuda_redis    - Redis 7
```

### Сеть Docker:

**КРИТИЧЕСКИ ВАЖНО**: Все контейнеры ДОЛЖНЫ быть в сети `infra_appnet` (bridge network).

```bash
# Проверка сети контейнера
docker inspect cuda_api | grep NetworkMode

# Правильно: "NetworkMode": "infra_appnet"
# Неправильно: "NetworkMode": "host" или "default"
```

### DNS-резолвинг между контейнерами:

```python
# В коде используются DNS-имена контейнеров:
DATABASE_URL = "postgresql+asyncpg://postgres:PASSWORD@db:5432/cudacrimea"
REDIS_URL = "redis://redis:6379/0"

# НЕ используйте localhost или 127.0.0.1 внутри контейнеров!
```

### Учетные данные БД:

```
Host: db (внутри Docker), 5.83.140.80 (снаружи)
Port: 5432
User: postgres
Password: plUUI1PLTktZ9uW2WE23b+ixNwJjJGwBDJPQEQFBE+vfmH0JP503wr5INS1poWg
Database: cudacrimea
```

**ОШИБКА**: НЕ используйте `cudacrimea:cudapass` - это старые неправильные креды!

### SSH доступ:

```bash
# Windows (PowerShell/CMD)
ssh -i "C:\Users\sanve\.ssh\cudacrimea_key" -o StrictHostKeyChecking=no root@5.83.140.80

# Пароль для root@5.83.140.80
91LHdsru:T.9T7
```

---

## КРИТИЧЕСКИЕ ОСОБЕННОСТИ

### 1. Redis Master/Slave Режим

**ПРОБЛЕМА**: Redis может переключиться в режим slave (реплика), становясь read-only.

```bash
# Проверка режима
docker exec cuda_redis redis-cli INFO replication | grep role

# Если видите role:slave - это проблема!
# Решение:
docker exec cuda_redis redis-cli REPLICAOF NO ONE
```

### 2. Поля моделей SQLAlchemy

**TelegramChannel модель:**
```python
# ПРАВИЛЬНО
channel.status == "active"  # Поле status: "active" | "paused" | "error"

# НЕПРАВИЛЬНО
channel.is_active  # Этого поля НЕТ!
```

**Event модель:**
```python
# Поля для изображений
event.image_url      # Основное изображение (str)
event.images         # Галерея (JSONB array)

# EventImage - отдельная таблица для галереи
```

### 3. UGC Submissions - Две системы хранения

События из парсеров сохраняются в **ДВЕ** системы одновременно:

1. **Redis Lists** (старая система):
   - `ugc:queue` - обычная очередь
   - `ugc:queue:paid` - платные события
   - `ugc:queue:parser` - из парсеров

2. **PostgreSQL ugc_submissions** (новая система):
   - Telegram Parser → ugc_submissions (status="parsed")
   - Universal Parser → ugc_submissions (status="parsed")

**ВАЖНО**: При отображении очереди `/admin/ugc` читаем из ОБЕИХ источников!

```python
# Читаем из Redis
items_raw = await redis.lrange("ugc:queue:parser", 0, 199)

# И из PostgreSQL
stmt = select(UGCSubmission).where(UGCSubmission.status == "parsed")
ugc_submissions = result.scalars().all()
```

### 4. Router Prefixes в FastAPI

**ОШИБКА**: Роутеры монтировались с дублированием префикса.

```python
# НЕПРАВИЛЬНО (приводит к /admin/admin/parsers)
app.include_router(parsers_router, prefix="/admin/parsers")

# ПРАВИЛЬНО (app уже монтирован в main.py на /admin)
app.include_router(parsers_router, prefix="/parsers")
```

### 5. Docker Logs - Ротация обязательна!

**ПРОБЛЕМА**: Логи могут вырасти до 22GB и забить диск, вызвав 100% CPU.

**Решение**: Настроен лимит в `/etc/docker/daemon.json`:

```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
```

Очистка логов:
```bash
# Найти путь к логам
docker inspect cuda_worker | grep LogPath

# Очистить
truncate -s 0 /var/lib/docker/containers/CONTAINER_ID/CONTAINER_ID-json.log

# Перезагрузить Docker
systemctl restart docker
```

### 6. OpenAI Package

**ОШИБКА**: `No module named 'openai'`

```bash
# Установка в контейнер
docker exec cuda_api pip install openai==1.51.2
docker exec cuda_worker pip install openai==1.51.2
```

---

## ЧАСТЫЕ ОШИБКИ И РЕШЕНИЯ

### Ошибка 1: 502 Bad Gateway на /admin

**Причина**: API-контейнер в неправильной сети или упал.

**Диагностика**:
```bash
# Проверить статус
docker ps | grep cuda_api

# Проверить сеть
docker inspect cuda_api | grep -A 10 Networks

# Проверить логи
docker logs cuda_api --tail 50
```

**Решение**:
```bash
# Пересоздать контейнер в правильной сети
docker rm -f cuda_api
docker run -d \
  --name cuda_api \
  --network infra_appnet \
  --network-alias api \
  -p 8000:8000 \
  -v /opt/cudaCrimea:/app \
  python:3.11 \
  bash -c "cd /app && pip install -r requirements.txt && uvicorn app.admin.main:app --host 0.0.0.0 --port 8000 --reload"
```

### Ошибка 2: Database Authentication Failed

**Причина**: Неправильные креды.

**Решение**: Используйте правильный пароль:
```
plUUI1PLTktZ9uW2WE23b+ixNwJjJGwBDJPQEQFBE+vfmH0JP503wr5INS1poWg
```

### Ошибка 3: События не появляются в очереди

**Причины**:
1. Redis в режиме slave (read-only)
2. Нет tg_account_id в Redis
3. Worker не запущен или упал

**Диагностика**:
```bash
# 1. Проверить Redis
docker exec cuda_redis redis-cli INFO replication | grep role
# Должно быть: role:master

# 2. Проверить tg_account_id
docker exec cuda_redis redis-cli GET tg_account_id
# Должно быть: e0e2b574-d997-4385-8ba6-1e97353774c3

# 3. Проверить worker
docker logs cuda_worker --tail 50 | grep -E "worker.started|schedule"
```

**Решение**:
```bash
# Redis в slave
docker exec cuda_redis redis-cli REPLICAOF NO ONE

# Нет tg_account_id
docker exec cuda_redis redis-cli SET tg_account_id e0e2b574-d997-4385-8ba6-1e97353774c3

# Worker упал
docker restart cuda_worker
```

### Ошибка 4: AttributeError при парсинге Telegram

**Текст ошибки**: `'TelegramChannel' object has no attribute 'is_active'`

**Причина**: Код использует старое поле `is_active`, а в модели поле `status`.

**Решение**:
```python
# Заменить все вхождения
channel.is_active → channel.status == "active"
```

### Ошибка 5: Изображения не извлекаются

**Причина**: Парсер не извлекает images из HTML.

**Решение**: Используйте функцию `extract_image_urls()` в universal_parser.py:

```python
def extract_image_urls(html: str, base_url: str) -> list[str]:
    """Извлечь URL изображений из HTML."""
    from urllib.parse import urljoin
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, 'html.parser')
    image_urls = []

    for img in soup.find_all('img'):
        src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
        if src:
            absolute_url = urljoin(base_url, src)
            # Фильтр иконок, логотипов, маленьких изображений
            if not any(x in absolute_url.lower() for x in ['icon', 'logo', 'avatar', 'pixel', '1x1']):
                image_urls.append(absolute_url)

    return image_urls[:20]
```

### Ошибка 6: ModuleNotFoundError после удаления файлов

**Текст ошибки**: `ModuleNotFoundError: No module named 'app.ingestors.normalize'`

**Причина**: При очистке проекта были удалены файлы, которые используются активными парсерами.

**Критически важные файлы, которые НЕЛЬЗЯ удалять**:
- `app/ingestors/normalize.py` - используется kudago, yandex, goroda, kassa24
- `app/ingestors/ai_parser_base.py` - используется afisha_goroda, kassa24
- `app/ingestors/migrate_html_parsers.py` - используется afisha_goroda, kassa24
- `app/ingestors/contact_extractor.py` - используется ai_parser_base

**Решение**: Восстановить файлы из git истории:
```bash
# Найти последний коммит с файлом
git log --all --full-history --oneline -- app/ingestors/normalize.py

# Восстановить файл
git show <commit_hash>^:app/ingestors/normalize.py > app/ingestors/normalize.py

# Закоммитить и задеплоить
git add app/ingestors/normalize.py
git commit -m "Restore normalize.py required by active parsers"
git push origin main
ssh root@5.83.140.80 "cd /opt/cudaCrimea && git pull && docker restart cuda_worker"
```

### Ошибка 7: Парсеры запланированы но не выполняются

**Текст в логах**: Job scheduled, но нет "Running job" записей

**Причина**: `IntervalTrigger` с `jitter` не выполняет первый запуск немедленно.

**Решение**: Добавить `next_run_time=datetime.now()` при создании джобов:
```python
scheduler.add_job(
    job_tg_channel,
    IntervalTrigger(minutes=interval, jitter=min(300, interval * 60 // 10)),
    id=f"tg_{channel.id}",
    args=[str(channel.id)],
    replace_existing=True,
    next_run_time=datetime.now(),  # ← Это критично!
)
```

**Файл**: `app/ingestors/worker.py` строки 395, 448

### Ошибка 8: Worker не загружает runtime_config

**Симптом**: `rc.get("tg_account_id")` возвращает `None`, хотя в `settings.json` значение есть.

**Причина**: Worker не вызывает `rc.load_from_file()` при старте.

**Решение**: Добавить загрузку конфига:
```python
async def main_async() -> None:
    s = get_settings()
    setup_logging(s.log_level)

    # Загрузить runtime config из settings.json
    rc.load_from_file()

    scheduler = AsyncIOScheduler()
    await _schedule_jobs(scheduler)
```

**Файл**: `app/ingestors/worker.py` строки 458, 464

### Ошибка 9: "Replacement index 0 out of range for positional args tuple"

**Причина**: Логирование текста/JSON с фигурными скобками `{}` которые structlog интерпретирует как плейсхолдеры форматирования.

**Решение**: Заменить `{}` на `[]` перед логированием:
```python
# ПЛОХО - вызовет ошибку если в тексте есть {}
logger.info("processing", text=text[:300])

# ХОРОШО - безопасно
safe_text = text[:300].replace("{", "[").replace("}", "]")
logger.info("processing", text=safe_text)
```

**Примеры в коде**:
- `app/ingestors/tg_channels.py:111` - логирование text_preview
- `app/ingestors/tg_channels.py:131` - логирование AI response

### Ошибка 10: Telegram парсер не находит события

**Симптом**: `posts_fetched: 50, events_saved: 0` в логах

**Возможные причины**:
1. AI возвращает пустой JSON `{}`
2. AI не распознает событие в тексте
3. Validation не проходит
4. Logger уровень debug скрывает `tg.extract.no_event`

**Диагностика**: Включить подробное логирование:
```python
# Изменить logger.debug на logger.info
if not extracted or not extracted.get("title"):
    logger.info("tg.extract.no_event", channel=channel, extracted_data=extracted)  # было debug
    return None

# Добавить логирование AI ответа
logger.info("tg.extract.ai_raw_response", channel=channel, response=safe_response)
```

**Возможные решения**:
1. Проверить и улучшить TELEGRAM_PARSER_PROMPT
2. Увеличить `temperature` с 0.1 до 0.3-0.5
3. Попробовать другую модель (gpt-4o вместо gpt-4o-mini)
4. Добавить примеры в промпт (few-shot learning)

---

## СТРУКТУРА БАЗЫ ДАННЫХ

### Основные таблицы:

#### events
```sql
id UUID PRIMARY KEY
title VARCHAR NOT NULL
date DATE NOT NULL
time TIME
city VARCHAR
venue_name VARCHAR
address VARCHAR
lat FLOAT
lon FLOAT
district VARCHAR
price_min INTEGER
price_max INTEGER
category VARCHAR  -- "concert", "theater", "sport", "exhibition", "other"
source VARCHAR    -- "kudago", "yandex", "ugc", "telegram", "manual"
source_url VARCHAR
image_url VARCHAR -- Основное изображение
images JSONB      -- Галерея изображений
created_at TIMESTAMP
updated_at TIMESTAMP
```

#### telegram_channels
```sql
id UUID PRIMARY KEY
username VARCHAR UNIQUE  -- Без @, например "eventcrimea"
title VARCHAR
status VARCHAR DEFAULT 'active'  -- "active" | "paused" | "error"
parse_interval_minutes INTEGER DEFAULT 45  -- Интервал парсинга (5-1440)
last_check_at TIMESTAMP
total_messages_seen INTEGER DEFAULT 0
total_parsed INTEGER DEFAULT 0
total_published INTEGER DEFAULT 0
created_at TIMESTAMP
```

#### ugc_submissions
```sql
id UUID PRIMARY KEY
raw_text TEXT
source_url VARCHAR
extracted_data JSONB        -- Структурированные данные от AI
is_ai_structured BOOLEAN
parser_source VARCHAR       -- "telegram" | "universal"
status VARCHAR DEFAULT 'parsed'  -- "parsed" | "approved" | "rejected"
approved_event_id UUID      -- FK to events.id
created_at TIMESTAMP
```

#### universal_parsers
```sql
id UUID PRIMARY KEY
name VARCHAR UNIQUE
url VARCHAR NOT NULL
parse_interval_minutes INTEGER DEFAULT 60
status VARCHAR DEFAULT 'active'
last_check_at TIMESTAMP
total_events_found INTEGER DEFAULT 0
created_at TIMESTAMP
```

### Миграции Alembic:

```bash
# Создать новую миграцию
cd /opt/cudaCrimea
docker exec cuda_api alembic -c app/db/alembic.ini revision --autogenerate -m "Description"

# Применить миграции
docker exec cuda_api alembic -c app/db/alembic.ini upgrade head

# Откатить последнюю
docker exec cuda_api alembic -c app/db/alembic.ini downgrade -1
```

**Важные миграции**:
- `0023_*` - Добавлена таблица ugc_submissions
- `0024_*` - Добавлено поле parse_interval_minutes в telegram_channels

---

## СИСТЕМЫ ПАРСИНГА

### 1. Telegram Parser (Telethon)

**Файл**: `app/ingestors/worker.py` → функция `job_tg_channel(channel_id)`

**Как работает**:
1. APScheduler создаёт отдельную задачу для каждого активного канала
2. Каждая задача запускается с индивидуальным интервалом (parse_interval_minutes)
3. Используется Telethon для подключения к Telegram
4. Парсит последние 50 сообщений
5. Передаёт в AI для извлечения событий
6. Сохраняет в ugc_submissions (status="parsed")

**Настройка Telegram Account**:

```bash
# ID аккаунта хранится в Redis
docker exec cuda_redis redis-cli GET tg_account_id
# Должен быть: e0e2b574-d997-4385-8ba6-1e97353774c3

# Проверка в БД
docker exec cuda_db psql -U postgres -d cudacrimea -c \
  "SELECT id, phone, api_id FROM telegram_accounts WHERE id='e0e2b574-d997-4385-8ba6-1e97353774c3';"
```

**Добавление канала через UI**:

1. Админ-панель → Парсеры → Вкладка "Telegram"
2. Заполнить:
   - Username (без @)
   - Интервал парсинга (5-1440 минут)
3. Бот автоматически вступает в канал/группу
4. Создаётся запись в telegram_channels
5. Worker автоматически создаёт APScheduler задачу

**Редактирование интервала**:

Через UI (модальное окно) или напрямую в БД:
```sql
UPDATE telegram_channels
SET parse_interval_minutes = 30
WHERE username = 'eventcrimea';
```

### 2. Universal Parser (AI + BeautifulSoup)

**Файл**: `app/ingestors/universal_parser.py`

**Как работает**:
1. Загружает HTML с любого URL
2. Извлекает изображения через `extract_image_urls()`
3. Очищает HTML (удаляет скрипты, стили, nav, footer)
4. Отправляет в GPT-4 с промптом для извлечения событий
5. AI возвращает JSON с событиями
6. Сохраняет в ugc_submissions (status="parsed")

**Промпт для AI** (UNIVERSAL_PARSER_PROMPT):

```
Ты - эксперт по извлечению информации о событиях из HTML.

ЗАДАЧА: Извлечь все события (концерты, спектакли, выставки, спорт) из HTML.

ФОРМАТ ОТВЕТА (JSON):
{
  "events": [
    {
      "title": "Название события",
      "date_iso": "2025-10-25",
      "time_24h": "19:00",
      "venue_name": "Название места",
      "address": "Полный адрес",
      "city": "Симферополь",
      "price_min": 500,
      "price_max": 1500,
      "category": "concert",
      "image_url": "URL основного изображения"
    }
  ]
}

КАТЕГОРИИ: concert, theater, sport, exhibition, festival, other

IMG_URLS будут предоставлены отдельно.
```

**Добавление парсера через UI**:

1. Админ-панель → Парсеры → Вкладка "Универсальный"
2. Заполнить:
   - Название (для идентификации)
   - URL страницы со списком событий
   - Интервал парсинга (минуты)
3. Нажать "Добавить парсер"

### 3. Ручные парсеры (KudaGo, Yandex, Goroda)

**Файлы**: `app/ingestors/kudago.py`, `yandex.py`, `goroda.py`

**Управление**: Через UI в разделе "Настройки" → Runtime Config

```json
{
  "ingest_kudago_enabled": true,
  "ingest_kudago_hours": "02:00",
  "ingest_kudago_cities": ["simferopol", "sevastopol"],

  "ingest_yandex_enabled": true,
  "ingest_yandex_hours": "03:00",

  "ingest_goroda_enabled": false
}
```

---

## АДМИН-ПАНЕЛЬ

### Структура роутов:

```
/admin                    - Главная (редирект на /ugc)
/admin/login             - Авторизация
/admin/logout            - Выход

/admin/events            - Список событий
/admin/events/new        - Создать событие
/admin/events/{id}/edit  - Редактировать событие

/admin/ugc               - Очередь модерации UGC
/admin/ugc/approve       - Подтвердить событие (POST, JSON)
/admin/ugc/reject        - Отклонить событие (POST, JSON)
/admin/ugc/bulk-delete   - Массовое удаление (POST, JSON)

/admin/parsers           - Управление парсерами
/admin/parsers/telegram  - Telegram-каналы
/admin/parsers/universal - Универсальные парсеры
/admin/archive           - Архив

/admin/settings          - Настройки (runtime config)
```

### Модерация UGC - Массовые действия

**Функционал**:
- ✅ Выбор нескольких событий чекбоксами
- ✅ Массовое подтверждение (кнопка "✅ Подтвердить")
- ✅ Массовое отклонение (кнопка "❌ Отклонить")
- ✅ Массовое удаление (кнопка "🗑️ Удалить")
- ✅ AI-обработка (кнопка "🤖 Обработать AI")

**Как работает**:

1. Пользователь выбирает события чекбоксами
2. Нажимает кнопку действия
3. JavaScript отправляет AJAX-запросы для каждого события
4. Карточки удаляются из DOM с анимацией
5. Показывается toast-уведомление (зелёное/красное)
6. **Без перезагрузки страницы!**

**Код уведомлений** (ugc.html):

```javascript
function showNotification(message, type = 'success') {
  const notification = document.createElement('div');
  notification.className = `notification-toast notification-${type}`;
  notification.textContent = message;
  document.body.appendChild(notification);

  setTimeout(() => notification.classList.add('show'), 10);
  setTimeout(() => {
    notification.classList.remove('show');
    setTimeout(() => notification.remove(), 300);
  }, 3000);
}
```

### CSRF Protection

**Все POST-запросы требуют CSRF-токен**:

```html
<!-- В форме -->
<input type="hidden" name="csrf" value="{{ request.session.get('csrf_token') }}">

<!-- В JavaScript -->
const csrf = document.querySelector('input[name="csrf"]').value;
fetch('/admin/ugc/approve', {
  method: 'POST',
  body: `csrf=${encodeURIComponent(csrf)}&raw=${encodeURIComponent(rawData)}`
});
```

---

## ДЕПЛОЙ И ОБСЛУЖИВАНИЕ

### Процесс деплоя (Windows → Linux сервер):

```powershell
# 1. Коммит изменений локально
git add .
git commit -m "Description"

# 2. Пуш на GitHub
git push origin main

# 3. Подключение к серверу и обновление
ssh -i "C:\Users\sanve\.ssh\cudacrimea_key" -o StrictHostKeyChecking=no root@5.83.140.80 "cd /opt/cudaCrimea && git pull origin main"

# 4. Перезапуск контейнеров (если нужно)
ssh -i "C:\Users\sanve\.ssh\cudacrimea_key" -o StrictHostKeyChecking=no root@5.83.140.80 "docker restart cuda_api cuda_worker"
```

### Когда перезапускать контейнеры:

- **cuda_api** - при изменении Python-кода (FastAPI auto-reload работает, но иногда зависает)
- **cuda_worker** - при изменении кода парсеров или worker.py
- **cuda_db** - НЕ перезапускать без необходимости!
- **cuda_redis** - только если проблемы с памятью/репликацией

### Проверка здоровья системы:

```bash
# Все контейнеры запущены?
docker ps

# Логи API
docker logs cuda_api --tail 100 --follow

# Логи Worker (парсеры)
docker logs cuda_worker --tail 100 --follow

# Проверка БД
docker exec cuda_db psql -U postgres -d cudacrimea -c "SELECT COUNT(*) FROM events;"

# Проверка Redis
docker exec cuda_redis redis-cli PING
docker exec cuda_redis redis-cli INFO replication
docker exec cuda_redis redis-cli GET tg_account_id

# Очередь UGC
docker exec cuda_redis redis-cli LLEN "ugc:queue:parser"
```

### Мониторинг парсеров:

```bash
# Последние события от Telegram Parser
docker exec cuda_db psql -U postgres -d cudacrimea -c \
  "SELECT id, parser_source, status, created_at FROM ugc_submissions
   WHERE parser_source='telegram'
   ORDER BY created_at DESC LIMIT 10;"

# Статистика по каналам
docker exec cuda_db psql -U postgres -d cudacrimea -c \
  "SELECT username, total_messages_seen, total_parsed, last_check_at
   FROM telegram_channels
   WHERE status='active';"

# Логи worker по парсерам
docker logs cuda_worker 2>&1 | grep -E "tg_channel|universal_parser" | tail -50
```

### Бэкап базы данных:

```bash
# Создать дамп
docker exec cuda_db pg_dump -U postgres cudacrimea > backup_$(date +%Y%m%d).sql

# Восстановить
docker exec -i cuda_db psql -U postgres cudacrimea < backup_20251025.sql
```

---

## ЧЕКЛИСТ ДЛЯ НОВОЙ СЕССИИ

Когда начинаешь работу с проектом после перерыва:

### ✅ Шаг 1: Проверить инфраструктуру

```bash
# Подключиться к серверу
ssh -i "C:\Users\sanve\.ssh\cudacrimea_key" -o StrictHostKeyChecking=no root@5.83.140.80

# Все контейнеры UP?
docker ps | grep cuda

# Правильная сеть?
docker inspect cuda_api | grep -A 5 Networks

# Redis в режиме master?
docker exec cuda_redis redis-cli INFO replication | grep role
```

### ✅ Шаг 2: Синхронизировать код

```bash
cd /opt/cudaCrimea
git status
git pull origin main
```

### ✅ Шаг 3: Проверить миграции

```bash
# Текущая версия БД
docker exec cuda_api alembic -c app/db/alembic.ini current

# Есть непримененные?
docker exec cuda_api alembic -c app/db/alembic.ini upgrade head
```

### ✅ Шаг 4: Проверить очереди и парсеры

```bash
# События в очереди модерации?
docker exec cuda_redis redis-cli LLEN "ugc:queue:parser"

# Активные каналы Telegram
docker exec cuda_db psql -U postgres -d cudacrimea -c \
  "SELECT username, status, parse_interval_minutes FROM telegram_channels;"

# Worker работает?
docker logs cuda_worker --tail 20 | grep -E "worker.started|schedule"
```

### ✅ Шаг 5: Прочитать последние коммиты

```bash
git log --oneline -10
```

---

## ДОПОЛНИТЕЛЬНЫЕ ЗАМЕТКИ

### AI Extraction Промпты

Для извлечения событий используется GPT-4. Важные детали:

1. **Температура**: 0.1 (для детерминированности)
2. **Модель**: gpt-4o или gpt-4-turbo
3. **Timeout**: 60 секунд
4. **Retry**: 3 попытки с exponential backoff

### Геокодирование

Адреса геокодируются через внешний API. Результаты кешируются в таблице `geocoding_cache`.

```sql
-- Проверка кеша
SELECT query, lat, lon, district, created_at
FROM geocoding_cache
WHERE query LIKE '%Пушкина%'
ORDER BY created_at DESC;
```

### Runtime Config

Настройки хранятся в Redis + JSON файл (`app/core/data/settings.json`).

**Изменение через UI автоматически**:
1. Обновляет Redis
2. Записывает в JSON файл
3. Worker читает при старте и каждые N минут

### Celery vs APScheduler

Проект использует **APScheduler** (не Celery!). Причины:
- Проще для небольших проектов
- Не требует брокера сообщений
- Встроенный scheduler в worker процесс

---

## КОНТАКТЫ И ССЫЛКИ

- **Сервер**: 5.83.140.80 (root, пароль: 91LHdsru:T.9T7)
- **GitHub**: https://github.com/asex9876/cudaCrimea.git
- **Admin Panel**: http://5.83.140.80:8000/admin
- **API Docs**: http://5.83.140.80:8000/docs

---

**Последнее обновление**: 2025-10-25
**Версия**: 1.0
**Автор**: Claude (Anthropic)

---

## БЫСТРЫЕ КОМАНДЫ (ШПАРГАЛКА)

```bash
# SSH
ssh -i "C:\Users\sanve\.ssh\cudacrimea_key" -o StrictHostKeyChecking=no root@5.83.140.80

# Логи
docker logs cuda_api --tail 50 --follow
docker logs cuda_worker --tail 50 --follow

# Перезапуск
docker restart cuda_api
docker restart cuda_worker

# Redis mode fix
docker exec cuda_redis redis-cli REPLICAOF NO ONE

# tg_account_id fix
docker exec cuda_redis redis-cli SET tg_account_id e0e2b574-d997-4385-8ba6-1e97353774c3

# БД connection
docker exec -it cuda_db psql -U postgres -d cudacrimea

# Деплой
cd /opt/cudaCrimea && git pull origin main && docker restart cuda_api cuda_worker

# Очистка логов
docker exec cuda_worker sh -c "truncate -s 0 /proc/1/fd/1"
```

