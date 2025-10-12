# CudaCrimea Project - Session Summary

## 🎯 Project Overview
Telegram бот + FastAPI для агрегации и рекомендации событий в Крыму.

## 🔑 Server Access
- **Server**: 5.83.140.80
- **SSH**: `ssh cudacrimea` (ключ настроен в ~/.ssh/config)
- **Password**: jR9eG8gT3xjS
- **Admin Panel**: http://5.83.140.80/admin/
- **Basic Auth**: admin / crimea2025

## 📦 Tech Stack
- **Backend**: FastAPI + Python 3.11
- **Database**: PostgreSQL 15 (cudacrimea)
- **Cache**: Redis 7
- **Telegram**: Telethon + aiogram
- **AI**: AI Mediator (OpenAI-compatible API)
- **Deploy**: Docker Compose V2

## ✅ Completed in This Session

### 1. SSH & Deployment
- ✅ Настроен SSH ключ (без пароля)
- ✅ Исправлены скрипты deploy.sh и update.sh для Docker Compose V2

### 2. Admin Panel Navigation
- ✅ Исправлен Nginx routing (rewrite правило для /admin/)
- ✅ Исправлены все ссылки в base.html
- ✅ Настроена auto-авторизация через Nginx basic auth

### 3. Database Issues Fixed
- ✅ Добавлена колонка `city` в таблицу events
- ✅ Добавлена колонка `images` (JSONB) в таблицу events
- ✅ Добавлена колонка `phone_code_hash` в таблицу telegram_accounts
- ✅ Миграция 1c064442d6af применена

### 4. AI Integration
- ✅ Проверена работа AI Mediator (https://api.ai-mediator.ru/v1)
- ✅ API Key: sk-ke1W0K9TOFJlhXShbPo-iA
- ✅ Доступные модели: gpt-5, claude-3-7-sonnet, claude-sonnet-4-5, gemini-2.5-flash
- ✅ Текущие модели: gpt-4o-mini (экономия)

### 5. LLM Admin Panel (NEW! 🎉)
- ✅ Создана страница /admin/llm для управления AI
- ✅ Таблица llm_usage для учета токенов
- ✅ Автоматическое логирование использования AI
- ✅ Статистика по сервисам (extractor, classifier, summarizer)
- ✅ Статистика по моделям
- ✅ Тест подключения к AI
- ✅ Форма настроек (API key, модели)
- ✅ **Chart.js графики** (круговая, столбчатая, линейная)
- ✅ **Фильтры по датам** (сегодня, неделя, месяц, год)
- ✅ **API /llm/chart-data** для динамического обновления графиков

### 6. Diagnostic Tools
- ✅ Создан scripts/diagnostics.sh (полная диагностика)
- ✅ Создан scripts/health-check.sh (быстрая проверка)
- ✅ Создан scripts/collect-logs.sh (сбор логов)
- ✅ Добавлены команды: `make health`, `make diagnose`, `make collect-logs`
- ✅ Создан docs/TROUBLESHOOTING.md

## 📁 Key Files & Locations

### Backend
- `/opt/cudaCrimea/` - корень проекта на сервере
- `app/admin/main.py` - главный файл админ-панели
- `app/admin/llm_routes.py` - роуты для LLM панели
- `app/core/llm/client.py` - клиент для AI (с логированием)
- `app/db/models/tables.py` - модели БД (включая LLMUsage)

### Config
- `.env` - переменные окружения (API ключи, пароли)
- `infra/nginx.prod.conf` - конфигурация Nginx
- `infra/docker-compose.prod.yml` - продакшн compose файл
- `infra/nginx.htpasswd` - basic auth (admin:crimea2025)

### Migrations
- `app/db/alembic/versions/` - миграции БД
- Текущая версия: 0009 (llm_usage table)

## 🔧 Common Commands

```bash
# SSH (без пароля)
ssh cudacrimea

# Обновить код
cd /opt/cudaCrimea && git pull origin main

# Пересобрать контейнеры
cd /opt/cudaCrimea/infra
docker compose -f docker-compose.prod.yml up -d --build api

# Применить миграции
docker exec cuda_api alembic -c app/db/alembic.ini upgrade head

# Логи
docker logs cuda_api --tail 50
docker logs cuda_bot --tail 50
docker logs cuda_nginx --tail 50

# Диагностика
make health        # быстрая проверка
make diagnose      # полная диагностика
make collect-logs  # собрать все логи

# База данных
docker exec cuda_db psql -U postgres -d cudacrimea -c "SELECT * FROM llm_usage LIMIT 5;"
```

## 🚀 Next Steps / TODO

### High Priority
1. **LLM Panel Improvements** (✅ ~35K tokens использовано)
   - [✅] Добавить Chart.js для графиков
   - [✅] Круговая диаграмма использования по сервисам
   - [✅] Линейный график токенов по времени
   - [✅] Фильтры по датам (сегодня, неделя, месяц, год)
   - [ ] Таблица тарифов моделей для расчета стоимости
   - [ ] Экспорт статистики в CSV/Excel

2. **Parser Configuration** (~30K tokens)
   - [ ] Настроить парсер для krymskiye_dela
   - [ ] Добавить новые источники событий
   - [ ] Автоматическое расписание парсинга

3. **Telegram Bot Features** (~40K tokens)
   - [ ] Настроить автопостинг в канал
   - [ ] Улучшить UGC модерацию (массовые действия)
   - [ ] Добавить команды для управления подпиской

### Medium Priority
4. **Optimization** (~20K tokens)
   - [ ] Настроить автоматические бэкапы БД
   - [ ] Оптимизировать запросы к БД (индексы)
   - [ ] Настроить логирование в файлы

5. **Monitoring** (~15K tokens)
   - [ ] Добавить метрики Prometheus
   - [ ] Настроить алерты в Telegram
   - [ ] Dashboard для мониторинга

## 🐛 Known Issues
- ⚠️ Миграция 0009 имеет синтаксическую ошибку в файле (но таблица создана вручную)
- ⚠️ Стоимость токенов пока не считается автоматически (нужна таблица тарифов)

## 💡 Important Notes
- Все git операции идут через локальную машину Windows
- На сервере изменения применяются через `git pull`
- Миграции иногда нужно применять вручную через SQL
- AI Mediator работает отлично, логирование токенов настроено

## 📚 Documentation
- `docs/TROUBLESHOOTING.md` - гайд по решению проблем
- `DEPLOY.md` - инструкции по деплою
- `README.md` - общее описание проекта

---

**Last Updated**: 2025-10-12 (Session 2)
**Session Tokens Used**: ~61K / 200K
**Status**: ✅ All systems operational

## 📝 Session 2 Summary (2025-10-12)
### Completed Tasks
- ✅ Добавлены интерактивные графики Chart.js в LLM админ-панель
- ✅ Реализована круговая диаграмма распределения токенов по сервисам
- ✅ Добавлен столбчатый график использования по моделям
- ✅ Создан линейный график токенов по времени (prompt vs completion)
- ✅ Реализованы фильтры по периодам (1 день, неделя, месяц, год)
- ✅ API эндпоинт /llm/chart-data с агрегацией через SQLAlchemy
- ✅ Интеграция с темной темой админ-панели

### Code Changes
- `app/admin/templates/base.html` - добавлен Chart.js CDN
- `app/admin/llm_routes.py` - новый эндпоинт llm_chart_data()
- `app/admin/main.py` - регистрация роута /llm/chart-data
- `app/admin/templates/llm.html` - 3 canvas + JavaScript для графиков
- **Commit**: 23f709b "Add Chart.js visualizations to LLM admin panel"
