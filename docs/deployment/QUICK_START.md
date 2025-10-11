# ⚡ Quick Start - cudaCrimea

Минимальная инструкция для быстрого запуска на новом сервере Ubuntu.

## 📋 Предварительные требования

- Ubuntu 20.04+
- Минимум 2GB RAM (рекомендуется 4GB)
- Root или sudo доступ

## 🚀 Установка за 5 минут

### 1. Установка Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
# Перелогиньтесь или выполните: newgrp docker
```

### 2. Клонирование репозитория

```bash
cd /opt
sudo git clone <your-repo-url> cudaCrimea
cd cudaCrimea
sudo chown -R $USER:$USER .
```

### 3. Настройка окружения

```bash
cp .env.example .env
nano .env
```

**Обязательно измените:**
- `BOT_TOKEN` - получите от @BotFather
- `TELEGRAM_API_ID` и `TELEGRAM_API_HASH` - получите на https://my.telegram.org
- `DB_PASSWORD` - придумайте надежный пароль
- `ADMIN_PASSWORD` - пароль для админки
- `ADMIN_SECRET` - сгенерируйте: `openssl rand -hex 32`
- `AI_MEDIATOR_API_KEY` - API ключ для LLM

### 4. Запуск

```bash
cd infra
docker compose build
docker compose up -d
docker compose exec api alembic upgrade head
```

### 5. Проверка

```bash
# Статус контейнеров
docker compose ps

# Логи
docker compose logs -f --tail 50

# Health check
curl http://localhost:8000/health
```

### 6. Первый вход в админку

```bash
# Создайте htpasswd для админки
cd /opt/cudaCrimea/infra
htpasswd -c nginx.htpasswd admin
# Введите пароль

# Перезапустите nginx
docker compose restart nginx

# Откройте в браузере
# http://your-server-ip/admin/
```

## 🔑 Настройка Telegram аккаунта для парсинга

1. Откройте админку: `http://your-server-ip/admin/`
2. Войдите (admin / ваш_пароль_из_htpasswd)
3. Перейдите в "Telegram аккаунты"
4. Нажмите "Добавить аккаунт"
5. Введите:
   - API ID (из .env)
   - API Hash (из .env)
   - Номер телефона (+7...)
6. Следуйте инструкциям для 2FA
7. После авторизации перейдите в "Парсеры"
8. Выберите авторизованный аккаунт
9. Настройте каналы для мониторинга

## ✅ Проверка работоспособности

```bash
# Проверьте что бот отвечает
# Найдите вашего бота в Telegram и отправьте /start

# Проверьте парсеры
make parser-telegram
# или
docker compose exec api python -m app.ingestors.telegram_channels

# Проверьте очередь UGC
# В админке: http://your-server-ip/admin/ugc-queue
```

## 🔄 Автоматический backup

```bash
# Сделайте скрипт исполняемым
chmod +x /opt/cudaCrimea/scripts/backup.sh

# Добавьте в cron
crontab -e
```

Добавьте строку:
```
0 3 * * * /opt/cudaCrimea/scripts/backup.sh >> /var/log/cudacrimea_backup.log 2>&1
```

## 🌐 Настройка домена (опционально)

```bash
# Установка certbot
sudo apt install -y certbot

# Получение SSL сертификата
sudo certbot certonly --standalone -d your-domain.com

# Копирование сертификатов
sudo mkdir -p /opt/cudaCrimea/infra/ssl
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem /opt/cudaCrimea/infra/ssl/
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem /opt/cudaCrimea/infra/ssl/
sudo chmod 644 /opt/cudaCrimea/infra/ssl/*

# Раскомментируйте SSL volume в docker-compose.yml
# Перезапустите nginx
cd /opt/cudaCrimea/infra
docker compose restart nginx
```

## 📊 Полезные команды

```bash
# Просмотр логов
make logs
make logs-api
make logs-bot

# Статус сервисов
make ps
make health

# Backup
make backup

# Обновление
make deploy

# Перезапуск
make restart

# Остановка
make down
```

## 🆘 Troubleshooting

### Контейнеры не запускаются
```bash
docker compose logs
docker compose down
docker compose build --no-cache
docker compose up -d
```

### Бот не отвечает
```bash
# Проверьте токен
cat .env | grep BOT_TOKEN

# Проверьте логи
docker compose logs bot

# Перезапустите бота
docker compose restart bot
```

### База данных не подключается
```bash
# Проверьте PostgreSQL
docker compose exec db psql -U postgres -c "SELECT version();"

# Проверьте пароль в .env
cat .env | grep DB_PASSWORD
```

### Фотографии не отображаются
```bash
# Проверьте uploads
docker exec cuda_api ls -lah /app/app/uploads/

# Проверьте nginx
docker compose logs nginx

# Перезапустите nginx
docker compose restart nginx
```

## 📚 Дополнительная документация

- **[DEPLOY.md](DEPLOY.md)** - Полная инструкция по развертыванию
- **[DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md)** - Чеклист для проверки
- **[README.md](README.md)** - Документация проекта
- **[CHANGELOG.md](CHANGELOG.md)** - История изменений

---

**🎉 Готово! Ваш бот должен работать!**

Telegram бот: `@your_bot_username`
Админка: `http://your-server-ip/admin/`
API: `http://your-server-ip:8000`
Метрики: `http://your-server-ip/metrics`
