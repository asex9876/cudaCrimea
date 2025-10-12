# Troubleshooting Guide

Руководство по решению типичных проблем при работе с cudaCrimea.

## 🔧 Диагностические инструменты

### Быстрая проверка

```bash
# Быстрая проверка здоровья системы (выполняется за ~5 секунд)
make health

# Или напрямую
bash scripts/health-check.sh
```

**Exit code:** 0 = OK, 1 = Проблемы найдены

### Полная диагностика

```bash
# Комплексная проверка всех компонентов (~30 секунд)
make diagnose

# Или напрямую
bash scripts/diagnostics.sh
```

Проверяет:
- ✅ Docker установка и версия
- ✅ Статус контейнеров и health checks
- ✅ Доступность сервисов (DB, Redis, API)
- ✅ Сетевое подключение между сервисами
- ✅ Конфигурационные файлы (.env, nginx)
- ✅ Права доступа и volumes
- ✅ Последние ошибки в логах
- ✅ Использование диска

### Сбор логов для отладки

```bash
# Собрать все логи и информацию в один файл
make collect-logs

# Указать имя выходного файла
bash scripts/collect-logs.sh my_debug.txt
```

Создает файл с:
- Логами всех контейнеров (последние 500 строк)
- Docker состоянием
- Системной информацией
- Конфигурацией (секреты скрыты)
- БД и Redis статусом

**Этот файл можно отправить для анализа.**

---

## 🐛 Частые проблемы

### 1. Админка не открывается или показывает одну страницу

**Симптомы:**
- URL меняется при клике на меню, но содержимое не меняется
- Все страницы показывают "Быстрые ссылки"

**Причина:**
- API контейнер запускает REST API вместо админ-приложения
- Неправильная навигация в HTML шаблонах

**Решение:**

```bash
# 1. Проверить, что запущено
docker logs cuda_api --tail 20

# Должно быть: "uvicorn app.admin.main:app"
# Если видите "uvicorn app.api.main:app" - это проблема

# 2. Исправить docker-compose.prod.yml
cd infra
# Измените команду на: uvicorn app.admin.main:app --host 0.0.0.0 --port 8000

# 3. Перезапустить
docker compose -f docker-compose.prod.yml restart api

# 4. Проверить
curl http://localhost/admin/
```

### 2. Бот не запускается (Unauthorized)

**Симптомы:**
```
TelegramUnauthorizedError: Telegram server says - Unauthorized
```

**Причины:**
1. Неправильный `BOT_TOKEN` в `.env`
2. Бот запущен одновременно локально и на сервере
3. Бот удалён в @BotFather

**Решение:**

```bash
# 1. Проверить токен через API
curl https://api.telegram.org/bot<YOUR_TOKEN>/getMe

# Если ошибка 401 - токен неправильный

# 2. Получить новый токен от @BotFather
# - Отправьте /mybots в Telegram
# - Выберите бота → API Token

# 3. Обновить .env
nano .env
# BOT_TOKEN=новый_токен

# 4. Убедиться что локально бот остановлен
# На локальной машине:
docker compose down

# 5. Перезапустить на сервере
docker compose -f docker-compose.prod.yml restart bot

# 6. Проверить логи
docker logs cuda_bot -f
```

### 3. База данных не запускается

**Симптомы:**
```
Database is uninitialized and superuser password is not specified
```

**Решение:**

```bash
# 1. Проверить .env
cat .env | grep DB_PASSWORD

# Должно быть непустое значение

# 2. Если пусто, установить пароль
nano .env
# DB_PASSWORD=your_strong_password

# 3. Полностью пересоздать БД (удалит все данные!)
docker compose -f docker-compose.prod.yml down -v
docker compose -f docker-compose.prod.yml up -d

# 4. Применить миграции
docker compose -f docker-compose.prod.yml exec api alembic -c /app/app/db/alembic.ini upgrade head
```

### 4. Ошибки миграций

**Симптомы:**
```
KeyError: '0007'
Revision 0007 is not present
```

**Причина:**
Несоответствие ID миграций

**Решение:**

```bash
# 1. Проверить файлы миграций
docker compose exec api ls -la /app/app/db/alembic/versions/

# 2. Проверить ID в файле 0008
docker compose exec api head -20 /app/app/db/alembic/versions/0008_add_telegram_accounts.py | grep -E "Revision ID|down_revision"

# down_revision должен совпадать с ID в файле 0007

# 3. Если база новая, можно пометить все миграции как применённые
docker compose exec api alembic -c /app/app/db/alembic.ini stamp head
```

### 5. Фотографии из Telegram не отображаются

**Симптомы:**
- Фото загружаются, но в админке пустые

**Решение:**

```bash
# 1. Проверить nginx конфигурацию
cat infra/nginx.prod.conf | grep -A 10 "location /uploads"

# Должна быть секция:
# location /uploads/ {
#     proxy_pass $api_upstream/uploads/;
# }

# 2. Проверить StaticFiles в админке
docker compose exec api grep -n "mount.*uploads" /app/app/admin/main.py

# Должна быть строка:
# app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")

# 3. Перезапустить nginx и API
docker compose -f docker-compose.prod.yml restart nginx api
```

### 6. ENV переменная не загружается

**Симптомы:**
```
env: Input should be 'dev', 'test' or 'prod' [input_value='production']
```

**Решение:**

```bash
# 1. Проверить .env
cat .env | grep "^ENV="

# Должно быть: ENV=prod (НЕ production!)

# 2. Исправить
nano .env
# ENV=prod

# 3. Перезапустить контейнеры
docker compose -f docker-compose.prod.yml restart api bot worker
```

### 7. Контейнер постоянно перезапускается

**Решение:**

```bash
# 1. Посмотреть почему падает
docker logs <container_name> --tail 100

# 2. Проверить health check
docker inspect <container_name> | grep -A 20 Health

# 3. Проверить ресурсы
docker stats --no-stream

# 4. Если падает из-за OOM (нехватка памяти)
# Увеличить память для Docker или оптимизировать приложение
```

### 8. Nginx 502 Bad Gateway

**Причины:**
1. API контейнер не запущен
2. API контейнер запустился, но приложение упало
3. Неправильный upstream в nginx

**Решение:**

```bash
# 1. Проверить статус API
docker compose ps api

# 2. Проверить логи API
docker logs cuda_api --tail 50

# 3. Проверить что API слушает порт 8000
docker compose exec api netstat -tlnp | grep 8000
# или
docker compose exec api ss -tlnp | grep 8000

# 4. Проверить nginx upstream
docker compose exec nginx cat /etc/nginx/conf.d/default.conf | grep upstream

# 5. Тест прямого подключения
docker compose exec nginx curl http://api:8000/
```

---

## 📋 Чеклист для отладки

Когда что-то не работает, следуйте этому порядку:

### Шаг 1: Быстрая проверка
```bash
make health
```

### Шаг 2: Проверка контейнеров
```bash
docker compose ps
docker compose logs --tail=50
```

### Шаг 3: Проверка конфигурации
```bash
# Проверить .env
cat .env | grep -v "^#" | grep "="

# Проверить что используется правильный compose file
ls -la infra/docker-compose*.yml

# Проверить nginx конфиг
cat infra/nginx.prod.conf | head -50
```

### Шаг 4: Полная диагностика
```bash
make diagnose
```

### Шаг 5: Собрать логи для анализа
```bash
make collect-logs
```

---

## 🔍 Как читать логи

### Структура логов

**JSON логи (structlog):**
```json
{"module": "bot", "user_id": 123, "level": "info", "timestamp": "2025-10-11T22:26:42Z", "message": "bot.msg"}
```

**Uvicorn логи:**
```
INFO:     127.0.0.1:54321 - "GET /admin/events HTTP/1.1" 200 OK
```

### Уровни логирования

- `DEBUG` - Детальная информация для отладки
- `INFO` - Обычные события (запуск, обработка запросов)
- `WARNING` - Потенциальные проблемы
- `ERROR` - Ошибки, но приложение продолжает работать
- `CRITICAL` - Критические ошибки, приложение может упасть

### Поиск ошибок

```bash
# Все ошибки за последний час
docker logs cuda_api --since 1h 2>&1 | grep -i "error\|exception\|failed"

# Traceback Python ошибок
docker logs cuda_api --tail 200 | grep -A 10 "Traceback"

# Статистика по уровням логов
docker logs cuda_api 2>&1 | grep -o '"level":"[^"]*"' | sort | uniq -c
```

---

## 🚨 Экстренные действия

### Если всё сломалось

```bash
# 1. Остановить всё
docker compose -f infra/docker-compose.prod.yml down

# 2. Собрать логи ПЕРЕД удалением
bash scripts/collect-logs.sh emergency_$(date +%Y%m%d_%H%M%S).txt

# 3. Создать backup БД (если DB запущена)
bash scripts/backup.sh

# 4. Полная пересборка (УДАЛИТ volumes!)
docker compose -f infra/docker-compose.prod.yml down -v
docker compose -f infra/docker-compose.prod.yml build --no-cache
docker compose -f infra/docker-compose.prod.yml up -d

# 5. Применить миграции
docker compose -f infra/docker-compose.prod.yml exec api alembic -c /app/app/db/alembic.ini upgrade head

# 6. Проверить
make health
```

### Откат к рабочей версии

```bash
# 1. Посмотреть последние коммиты
git log --oneline -10

# 2. Откатиться к рабочему коммиту
git checkout <commit_hash>

# 3. Пересобрать
docker compose -f infra/docker-compose.prod.yml build --no-cache

# 4. Запустить
docker compose -f infra/docker-compose.prod.yml up -d
```

---

## 📞 Получить помощь

Если проблема не решается:

1. **Соберите логи:**
   ```bash
   make collect-logs
   ```

2. **Запустите диагностику:**
   ```bash
   make diagnose > diagnostics_output.txt
   ```

3. **Опишите проблему:**
   - Что пытались сделать
   - Что произошло вместо этого
   - Ошибки в логах
   - Приложите `logs_*.txt` и `diagnostics_output.txt`

4. **Проверьте документацию:**
   - [README.md](../README.md)
   - [docs/deployment/DEPLOY.md](deployment/DEPLOY.md)
   - [docs/development/GIT_WORKFLOW.md](development/GIT_WORKFLOW.md)

---

## 🛠 Полезные команды

```bash
# === Просмотр логов ===
make logs              # Все логи (follow mode)
make logs-api          # Только API
make logs-bot          # Только бот
docker logs cuda_api --tail 100 --follow

# === Перезапуск ===
make restart           # Все сервисы
docker compose restart api    # Только API

# === Shell в контейнер ===
docker compose exec api bash
docker compose exec db psql -U postgres cudacrimea

# === Проверка здоровья ===
make health            # Быстрая проверка
make diagnose          # Полная диагностика

# === Очистка ===
docker compose down    # Остановить
docker compose down -v # Остановить и удалить volumes
docker system prune -a # Очистить весь Docker (осторожно!)

# === БД ===
make migrate           # Применить миграции
make backup            # Создать backup
make restore file=backup_20251011.sql.gz  # Восстановить

# === Логи в файл ===
docker logs cuda_api > api.log 2>&1
make collect-logs      # Все логи в один файл
```

---

## ✅ Профилактика проблем

1. **Регулярные backup'ы:**
   ```bash
   # Добавить в crontab
   0 3 * * * cd /opt/cudaCrimea && make backup
   ```

2. **Мониторинг дискового пространства:**
   ```bash
   df -h
   docker system df
   ```

3. **Регулярные обновления:**
   ```bash
   git pull origin main
   docker compose -f infra/docker-compose.prod.yml build
   docker compose -f infra/docker-compose.prod.yml up -d
   ```

4. **Проверка логов на ошибки:**
   ```bash
   make health  # Раз в день
   ```

5. **Ротация логов Docker:**
   Добавить в `/etc/docker/daemon.json`:
   ```json
   {
     "log-driver": "json-file",
     "log-opts": {
       "max-size": "10m",
       "max-file": "3"
     }
   }
   ```
