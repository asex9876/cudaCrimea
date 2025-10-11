# История изменений cudaCrimea

## [Unreleased] - 2025-10-11

### 🚀 Production готовность

#### Добавлено
- **Docker Compose улучшения для production:**
  - Health checks для всех сервисов
  - Автоматический перезапуск контейнеров (`restart: unless-stopped`)
  - Зависимости с условиями health check
  - Персистентное хранилище для uploads (`uploads` volume)
  - Параметризация пароля БД через переменную окружения
  - Поддержка HTTPS (порт 443)

- **Telegram парсинг:**
  - Загрузка фотографий из Telegram сообщений
  - Хранение фотографий в `/app/uploads/`
  - Маунт `/uploads` в FastAPI для раздачи статических файлов
  - Nginx конфигурация для проксирования `/uploads/`
  - Исправлены ошибки с timezone (timezone-aware datetime)
  - Выбор Telegram аккаунта для парсинга через runtime config

- **Admin панель:**
  - Динамические уведомления (toast notifications) вместо редиректов
  - AJAX отправка форм для парсеров
  - Визуальный выбор Telegram аккаунта с аватарами
  - Настройка периодичности запуска парсеров

- **Backup и восстановление:**
  - Скрипт автоматического backup БД (`scripts/backup.sh`)
  - Скрипт восстановления из backup (`scripts/restore.sh`)
  - Сжатие backup'ов (gzip)
  - Автоматическое удаление старых backup'ов (7+ дней)
  - Интеграция с Makefile (`make backup`, `make restore`)

- **Документация:**
  - Подробная инструкция по развертыванию (`DEPLOY.md`)
  - Чеклист развертывания (`DEPLOYMENT_CHECKLIST.md`)
  - Обновленный README с инструкциями Docker и deployment
  - Улучшенный Makefile с категоризированными командами

- **Makefile команды:**
  - `make help` - справка по всем командам
  - `make deploy` - автоматическое развертывание обновлений
  - `make backup` / `make restore` - управление backup'ами
  - `make health` - проверка здоровья сервисов
  - `make logs-*` - просмотр логов отдельных сервисов
  - `make migrate-*` - управление миграциями
  - `make admin-*` - работа с админ-панелью

#### Исправлено
- **Timezone ошибки в Telegram парсере:**
  - Использование `datetime.now(timezone.utc)` вместо `datetime.now()`
  - Добавление `tzinfo=timezone.utc` при создании datetime объектов
  - Исправлено сравнение timezone-aware и timezone-naive дат

- **Загрузка фотографий:**
  - Загрузка полноразмерных фотографий вместо превью
  - Проверка существования и размера загруженных файлов
  - Удаление пустых файлов

- **Runtime config в парсерах:**
  - Использование `tg_account_id` для выбора Telegram аккаунта
  - Сохранение ID выбранного аккаунта в runtime config
  - Fallback на любой активный аккаунт если не выбран

- **Admin панель:**
  - JSON responses вместо редиректов для AJAX запросов
  - Исправлена ошибка Jinja2 с `str()` → `|string` filter
  - Сохранение `tg_account_id` через `set_many()` вместо `set()`

#### Изменено
- **nginx конфигурация:**
  - Добавлен location `/uploads/` для проксирования загруженных файлов
  - Подготовка для HTTPS (порт 443, комментированный SSL volume)

- **.gitignore:**
  - Исключение `app/uploads/` и загруженных изображений
  - Исключение `infra/nginx.htpasswd` (пароли)
  - Исключение `app/core/data/settings.json` (runtime config с секретами)
  - Исключение SSL сертификатов и приватных ключей

- **docker-compose.yml:**
  - Использование `${DB_PASSWORD}` вместо hardcoded пароля
  - Добавлен volume `uploads` для персистентности
  - Health checks для db, redis, api, nginx
  - Улучшенные depends_on с condition: service_healthy

### 🔒 Безопасность
- Параметризация всех паролей через .env
- Рекомендации по изменению ADMIN_SECRET, DB_PASSWORD
- Исключение секретных файлов из git
- Инструкции по настройке firewall

### 📚 Документация
- Полная инструкция по deployment на production сервер
- Настройка SSL с Let's Encrypt
- Автоматизация backup через cron
- Troubleshooting распространенных проблем
- Оптимизация PostgreSQL и Redis для production

---

## [0.1.0] - Предыдущие версии

### Реализовано
- FastAPI backend с admin панелью
- Telegram bot (Aiogram v3)
- Worker для обработки очереди
- Парсеры событий (KudaGo, Yandex, Telegram)
- Авторизация Telegram аккаунтов для парсинга
- UGC модерация через админку
- Рекомендательная система
- Docker инфраструктура
- Nginx reverse proxy

---

## Планы на будущее

### TODO
- [ ] Автоматический деплой через CI/CD (GitHub Actions)
- [ ] Мониторинг с Prometheus + Grafana
- [ ] Алерты при падении сервисов (Alertmanager, Telegram)
- [ ] Rate limiting для API endpoints
- [ ] CDN для статических файлов и изображений
- [ ] Оптимизация изображений (WebP, resize, thumbnails)
- [ ] Полнотекстовый поиск событий (PostgreSQL FTS или Elasticsearch)
- [ ] Кэширование частых запросов (Redis)
- [ ] Логирование в централизованную систему (ELK stack)
- [ ] A/B тестирование рекомендаций
- [ ] Аналитика использования бота
- [ ] Push уведомления о новых событиях
- [ ] Multi-region deployment для отказоустойчивости

### В разработке
- Улучшение ML модели для рекомендаций
- Парсинг дополнительных источников
- Интеграция с соцсетями (VK, Instagram)
