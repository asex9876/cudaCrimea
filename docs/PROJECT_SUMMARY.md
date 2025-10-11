# 📊 Резюме проекта cudaCrimea

## 🎯 О проекте

**cudaCrimea** - Telegram бот для поиска событий и мероприятий в Крыму (Севастополь, Симферополь, Ялта) с персонализированными рекомендациями на основе интересов пользователя.

## 🏗️ Архитектура

```
┌─────────────────┐
│  Telegram Bot   │ ← Пользователи
│   (Aiogram v3)  │
└────────┬────────┘
         │
    ┌────▼─────┐
    │   API    │ ← Admin панель
    │ FastAPI  │
    └────┬─────┘
         │
    ┌────▼──────────────────┐
    │   PostgreSQL 15       │ ← Хранение данных
    │   Redis 7             │ ← Очереди + кэш
    └───────────────────────┘
         │
    ┌────▼─────────┐
    │    Worker    │ ← Обработка UGC
    │   + Parsers  │ ← Сбор событий
    └──────────────┘
```

## 🔧 Технологический стек

### Backend
- **Python 3.11+**
- **FastAPI** - REST API + Admin панель
- **SQLAlchemy 2.x** - ORM для PostgreSQL
- **Alembic** - Миграции БД
- **Pydantic v2** - Валидация данных

### Bot
- **Aiogram v3** - Асинхронный Telegram bot framework
- **Redis** - Очереди сообщений и кэширование

### Парсинг
- **Telethon** - Парсинг Telegram каналов
- **httpx** - HTTP клиент для API
- **BeautifulSoup4** - HTML парсинг
- **Playwright** - Headless браузер для динамических сайтов

### Инфраструктура
- **Docker** + **Docker Compose** - Контейнеризация
- **nginx** - Reverse proxy + статика
- **PostgreSQL 15** - Основная БД
- **Redis 7** - Кэш + очереди

### Мониторинг
- **structlog** - Структурированное логирование
- **Prometheus metrics** - Метрики приложения

## 📂 Структура проекта

```
cudaCrimea/
├── app/
│   ├── api/              # FastAPI REST API
│   ├── bot/              # Telegram bot (Aiogram)
│   ├── admin/            # Admin панель (FastAPI + Jinja2)
│   ├── ingestors/        # Парсеры событий
│   ├── core/             # Бизнес-логика, конфиги
│   ├── db/               # Модели SQLAlchemy, миграции
│   └── scripts/          # Утилиты (seed, init_db)
├── infra/
│   ├── docker-compose.yml   # Оркестрация контейнеров
│   ├── Dockerfile.*         # Образы для сервисов
│   ├── nginx.conf           # Конфигурация nginx
│   └── nginx.htpasswd       # Basic auth для админки
├── scripts/
│   ├── backup.sh         # Автоматический backup БД
│   └── restore.sh        # Восстановление из backup
├── tests/                # Тесты (pytest)
├── .env.example          # Шаблон переменных окружения
├── Makefile              # Команды для управления проектом
├── DEPLOY.md             # Полная инструкция по развертыванию
├── DEPLOYMENT_CHECKLIST.md  # Чеклист для деплоя
└── README.md             # Основная документация
```

## ✨ Основные возможности

### Для пользователей (Telegram bot)
- 🔍 Поиск событий по городу и категории
- 🎯 Персонализированные рекомендации на основе интересов
- 📅 Фильтрация по дате и времени
- 💰 Фильтр по цене (бесплатные/платные)
- 📍 Сортировка по геолокации пользователя
- 🖼️ Просмотр фото событий
- ⭐ Сохранение избранных событий
- 📲 Отправка предложений о новых событиях (UGC)

### Для администраторов (Admin панель)
- 📊 Статистика использования бота
- ✅ Модерация UGC предложений
- 🤖 Управление Telegram аккаунтами для парсинга
- ⚙️ Настройка парсеров (города, каналы, периодичность)
- 📋 Управление событиями (CRUD)
- 🏢 Управление площадками и местами
- 📢 Управление рекламными размещениями
- 📌 Редакторские подборки и закрепления
- 👥 Управление пользователями бота

### Парсеры событий
- **KudaGo API** - Официальный API событий
- **Yandex.Afisha** - Парсинг через Playwright
- **Telegram каналы** - Мониторинг событийных каналов
- **Afisha Goroda** - Локальные афиши городов
- **Custom парсеры** - Легко добавить новые источники

## 🚀 Готовность к production

### ✅ Реализовано

#### Infrastructure
- [x] Docker Compose с health checks
- [x] Автоматический перезапуск контейнеров
- [x] Персистентное хранилище для БД, Redis, uploads
- [x] nginx reverse proxy с basic auth
- [x] Готовность к HTTPS (SSL)
- [x] Параметризация через .env
- [x] Изоляция сети между контейнерами

#### Database & Backup
- [x] PostgreSQL 15 с health checks
- [x] Миграции через Alembic
- [x] Автоматический backup скрипт
- [x] Восстановление из backup
- [x] Ротация старых backup'ов

#### Security
- [x] Параметризация всех паролей
- [x] Basic auth для админки
- [x] .gitignore для секретных файлов
- [x] Рекомендации по firewall
- [x] Изоляция портов БД и Redis

#### Monitoring & Logging
- [x] Структурированное логирование (JSON)
- [x] Prometheus метрики
- [x] Health check endpoints
- [x] Docker logs для всех сервисов

#### Documentation
- [x] Подробная инструкция по deployment
- [x] Чеклист развертывания
- [x] README с quick start
- [x] Makefile с документированными командами
- [x] Troubleshooting guide

#### DevOps
- [x] Makefile для автоматизации задач
- [x] Скрипты backup/restore
- [x] Готовность к CI/CD

### 🔄 Процесс развертывания

```bash
# 1. Подготовка
cp .env.example .env
nano .env  # Настройка секретов

# 2. Запуск
make build
make up
make migrate

# 3. Мониторинг
make logs
make health

# 4. Backup
make backup  # Ручной backup
crontab -e   # Автоматический backup в cron
```

## 📈 Масштабируемость

### Текущая конфигурация
- **Рекомендуемый сервер:** 4GB RAM, 2 CPU, 20GB disk
- **Concurrent пользователи:** ~1000
- **События в БД:** ~10,000
- **Парсинг:** ~1000 событий/день

### Планы масштабирования
- Горизонтальное масштабирование API (multiple replicas)
- Read replicas для PostgreSQL
- Redis Cluster для распределенного кэша
- CDN для статических файлов
- Message queue (RabbitMQ/Kafka) для высоконагруженных задач

## 🔐 Безопасность

### Implemented
- Basic auth для админки
- CSRF protection
- SQL injection protection (SQLAlchemy ORM)
- XSS protection (Jinja2 auto-escaping)
- Rate limiting (nginx level)
- Password hashing (htpasswd)

### Recommended for production
- HTTPS с Let's Encrypt
- Firewall (ufw/iptables)
- Fail2ban для SSH
- Regular security updates
- Database encryption at rest
- Backup encryption

## 📊 Метрики

### API
- Request count по endpoints
- Request duration
- Error rate
- Active connections

### Bot
- Active users (DAU/MAU)
- Messages processed
- Commands usage
- Event views/clicks

### Parsers
- Events parsed per source
- Parse duration
- Error rate
- Deduplicate rate

## 🛠️ Доступные команды (Makefile)

```bash
# Docker
make up              # Запустить контейнеры
make down            # Остановить и удалить
make restart         # Перезапустить
make logs            # Просмотр логов
make health          # Проверка health

# Database
make migrate         # Применить миграции
make backup          # Создать backup
make restore         # Восстановить из backup

# Deployment
make deploy          # Развернуть обновление
make deploy-fresh    # Развернуть с нуля (ОПАСНО!)

# Development
make dev             # Запуск в dev режиме
make shell-api       # Shell контейнера API
make shell-db        # PostgreSQL shell
make test            # Запустить тесты
```

## 📚 Документация

- **[README.md](README.md)** - Основная документация, quick start
- **[DEPLOY.md](DEPLOY.md)** - Полная инструкция по развертыванию
- **[DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md)** - Чеклист для деплоя
- **[CHANGELOG.md](CHANGELOG.md)** - История изменений
- **[.env.example](.env.example)** - Документированные переменные окружения

## 🤝 Поддержка

При возникновении проблем:
1. Проверьте [DEPLOY.md](DEPLOY.md) секцию Troubleshooting
2. Проверьте логи: `make logs`
3. Проверьте health: `make health`
4. Создайте issue в репозитории

## 📄 Лицензия

[Укажите лицензию проекта]

---

**Версия:** 0.2.0
**Последнее обновление:** 2025-10-11
**Статус:** Production Ready ✅
