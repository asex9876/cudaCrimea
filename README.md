# Куда пойти: Крым/Севастополь

Telegram-бот для поиска событий и мест в Крыму и Севастополе. Автоматический парсинг событий из Telegram-каналов и сайтов, умные рекомендации на основе интересов пользователя.

## 📚 Документация

**Новичок?** Начните с [docs/INDEX.md](docs/INDEX.md) — навигация по всей документации проекта.

**Быстрый старт:**
- [docs/deployment/QUICK_START.md](docs/deployment/QUICK_START.md) — развернуть за 5 минут
- [docs/NEXT_STEPS.md](docs/NEXT_STEPS.md) — что делать прямо сейчас

**Полная документация:**
- [docs/deployment/](docs/deployment/) — развертывание на сервере
- [docs/development/](docs/development/) — разработка и Git workflow
- [docs/PROJECT_SUMMARY.md](docs/PROJECT_SUMMARY.md) — описание архитектуры

## 🛠 Стек технологий

- **Backend:** Python 3.11, FastAPI, Uvicorn
- **Bot:** Aiogram v3, Telethon (парсинг Telegram)
- **Database:** PostgreSQL 15, SQLAlchemy 2.x, Alembic
- **Cache/Queue:** Redis, RQ
- **Parsers:** httpx, Playwright, selectolax, BeautifulSoup4
- **Logging:** structlog (JSON), loguru, Sentry
- **Config:** Pydantic v2, python-dotenv
- **Utils:** rapidfuzz, python-dateutil, haversine

## 📂 Структура проекта

```
cudaCrimea/
├── app/
│   ├── api/          # FastAPI REST API
│   ├── bot/          # Telegram бот (Aiogram)
│   ├── admin/        # Веб админка (FastAPI + Jinja2)
│   ├── ingestors/    # Парсеры событий (Telegram, сайты)
│   ├── core/         # Бизнес-логика, конфиги
│   ├── db/           # SQLAlchemy модели, Alembic миграции
│   └── scripts/      # Утилиты (seed, backup, etc.)
├── infra/            # Docker конфигурация
├── docs/             # Документация
│   ├── deployment/   # Инструкции по развертыванию
│   └── development/  # Документация для разработчиков
├── tests/            # Тесты
└── scripts/          # Bash скрипты (backup, deploy)

## 🚀 Быстрый старт

### Локальная разработка

Требуется Python 3.11+ и Poetry.

```bash
# 1. Установка зависимостей
poetry install

# 2. Настройка окружения
cp .env.example .env
# Отредактируйте .env (BOT_TOKEN, DB credentials, etc.)

# 3. Линтеры (опционально)
poetry run pre-commit install

# 4. Запуск API
poetry run uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000
```

### Docker (Рекомендуется для локальной разработки)

```bash
# 1. Настройка окружения
cp .env.example .env
# Отредактируйте .env: BOT_TOKEN, DB_PASSWORD, ADMIN_PASSWORD, ADMIN_SECRET

# 2. Запуск всех сервисов
docker compose -f infra/docker-compose.yml up -d

# 3. Применение миграций
docker compose -f infra/docker-compose.yml exec api alembic upgrade head

# 4. Доступ к сервисам
# API: http://localhost:8000
# Админка: http://localhost/admin/
# Документация API: http://localhost:8000/docs
```

### Makefile команды (упрощают работу)

```bash
make help           # Список всех 40+ команд
make up             # Запустить контейнеры
make logs           # Просмотр логов (follow mode)
make migrate        # Применить миграции
make backup         # Создать backup БД
make health         # Проверить health всех сервисов
make deploy         # Развернуть обновление
```

Полный список команд: `make help` или смотрите [Makefile](Makefile)

## 📦 Развертывание на сервере

**Новичок?** → [docs/deployment/QUICK_START.md](docs/deployment/QUICK_START.md)
**Первый раз на сервере?** → [docs/deployment/SERVER_SETUP.md](docs/deployment/SERVER_SETUP.md)
**Полная инструкция** → [docs/deployment/DEPLOY.md](docs/deployment/DEPLOY.md)
**Чеклист** → [docs/deployment/DEPLOYMENT_CHECKLIST.md](docs/deployment/DEPLOYMENT_CHECKLIST.md)

### Краткая версия для опытных

```bash
# На сервере
curl -fsSL https://get.docker.com | sh
git clone <repo-url> /opt/cudaCrimea
cd /opt/cudaCrimea
cp .env.example .env && nano .env
make deploy
```

## ⚙️ Основные переменные окружения

Полный список в [.env.example](.env.example)

**Обязательные:**
- `BOT_TOKEN` — токен Telegram-бота
- `DATABASE_URL` — подключение к PostgreSQL
- `ADMIN_PASSWORD` — пароль админки
- `DB_PASSWORD` — пароль PostgreSQL

**Опциональные:**
- `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` — для парсинга Telegram
- `AI_MEDIATOR_API_KEY` — для LLM обработки событий
- `SENTRY_DSN` — для мониторинга ошибок

## 🔧 Разработка

**Git workflow:** [docs/development/GIT_WORKFLOW.md](docs/development/GIT_WORKFLOW.md)

```bash
# Форматирование кода
make fmt

# Линтер
make lint

# Тесты
make test

# Shell в контейнер API
make shell-api

# PostgreSQL shell
make shell-db
```

## 🏗️ Архитектура

**Сервисы (Docker Compose):**
- `api` — FastAPI (REST API + health checks)
- `bot` — Telegram бот (Aiogram v3)
- `worker` — Background worker для парсинга
- `db` — PostgreSQL 15
- `redis` — Redis 7 (кеш + очереди)
- `nginx` — Reverse proxy + статика

**Подробнее:** [docs/PROJECT_SUMMARY.md](docs/PROJECT_SUMMARY.md)

## 📝 Лицензия

MIT
