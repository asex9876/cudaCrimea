# 🖥️ Первоначальная настройка сервера

Пошаговая инструкция для первого развертывания cudaCrimea на чистом сервере.

## 📋 Что вам понадобится

- Сервер Ubuntu 20.04+ (VPS/Dedicated)
- SSH доступ к серверу
- Доменное имя (опционально, можно использовать IP)
- 30-60 минут времени

## 🚀 Шаг за шагом

### 1. Подключение к серверу

```bash
# С вашего компьютера
ssh root@your-server-ip
# или
ssh user@your-server-ip
```

### 2. Обновление системы

```bash
# Обновляем пакеты
sudo apt update && sudo apt upgrade -y

# Устанавливаем необходимые утилиты
sudo apt install -y curl git nano htop ufw
```

### 3. Настройка firewall

```bash
# Включаем firewall
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS
sudo ufw enable

# Проверяем
sudo ufw status
```

### 4. Установка Docker

```bash
# Устанавливаем Docker
curl -fsSL https://get.docker.com | sudo sh

# Добавляем пользователя в группу docker
sudo usermod -aG docker $USER

# ВАЖНО: Перелогиньтесь или выполните:
newgrp docker

# Проверяем установку
docker --version
docker compose version
```

### 5. Клонирование репозитория

**ВАЖНО:** Сначала нужно создать Git репозиторий!

#### На локальном компьютере:

```bash
# Перейдите в директорию проекта
cd "c:\Users\sanve\OneDrive\Рабочий стол\cudaCrimea"

# Создайте репозиторий на GitHub/GitLab
# Затем добавьте remote
git remote add origin https://github.com/ваш-username/cudaCrimea.git

# Первый коммит
git add .
git commit -m "Initial commit: Production ready"
git push -u origin master
```

#### На сервере:

```bash
# Клонируем репозиторий
cd /opt
sudo git clone https://github.com/ваш-username/cudaCrimea.git
sudo chown -R $USER:$USER cudaCrimea
cd cudaCrimea
```

### 6. Настройка .env файла

```bash
# Копируем example
cp .env.example .env

# Редактируем
nano .env
```

**Обязательно измените:**

```env
# Runtime
ENV=production
APP_NAME=Куда пойти: Крым/Севастополь

# Telegram
BOT_TOKEN=<получите от @BotFather>
TELEGRAM_API_ID=<получите на my.telegram.org>
TELEGRAM_API_HASH=<получите на my.telegram.org>

# Database - ОБЯЗАТЕЛЬНО СМЕНИТЕ!
DB_PASSWORD=<сгенерируйте: openssl rand -base64 24>
DATABASE_URL=postgresql+asyncpg://postgres:<тот-же-пароль>@db:5432/cudacrimea

# Redis
REDIS_URL=redis://redis:6379/0

# LLM (выберите один)
AI_MEDIATOR_API_KEY=<ваш ключ>
# или
OPENAI_API_KEY=<ваш ключ>

# Admin - ОБЯЗАТЕЛЬНО СМЕНИТЕ!
ADMIN_USER=admin
ADMIN_PASSWORD=<сгенерируйте: openssl rand -base64 16>
ADMIN_SECRET=<сгенерируйте: openssl rand -hex 32>
```

**Генерация безопасных паролей:**

```bash
# Генерация ADMIN_SECRET (32+ символов)
openssl rand -hex 32

# Генерация DB_PASSWORD
openssl rand -base64 24

# Генерация ADMIN_PASSWORD
openssl rand -base64 16
```

### 7. Создание nginx htpasswd

```bash
cd /opt/cudaCrimea/infra

# Устанавливаем apache2-utils (для htpasswd)
sudo apt install -y apache2-utils

# Создаём файл с паролем
htpasswd -c nginx.htpasswd admin
# Введите пароль (используйте ADMIN_PASSWORD из .env)

# Можно добавить дополнительных пользователей
htpasswd nginx.htpasswd moderator
```

### 8. Запуск проекта

```bash
cd /opt/cudaCrimea/infra

# Собираем образы
docker compose build

# Запускаем контейнеры
docker compose up -d

# Проверяем статус
docker compose ps
```

Вы должны увидеть что-то вроде:
```
NAME          STATUS           PORTS
cuda_api      Up (healthy)     0.0.0.0:8000->8000/tcp
cuda_bot      Up
cuda_db       Up (healthy)     0.0.0.0:5432->5432/tcp
cuda_nginx    Up (healthy)     0.0.0.0:80->80/tcp
cuda_redis    Up (healthy)     0.0.0.0:6379->6379/tcp
cuda_worker   Up
```

### 9. Применение миграций

```bash
# Применяем миграции БД
docker compose exec api alembic upgrade head
```

### 10. Проверка работоспособности

```bash
# Проверяем API
curl http://localhost:8000/health

# Смотрим логи
docker compose logs -f --tail 50

# Проверяем что контейнеры healthy
docker compose ps
```

### 11. Настройка Telegram аккаунта для парсинга

1. Откройте в браузере: `http://your-server-ip/admin/`
2. Войдите (admin / пароль из htpasswd)
3. Перейдите в "Telegram аккаунты"
4. Нажмите "Добавить аккаунт"
5. Введите:
   - API ID (из .env)
   - API Hash (из .env)
   - Номер телефона (+7...)
6. Введите код из Telegram
7. Если включена 2FA - введите пароль

### 12. Настройка парсеров

1. В админке перейдите в "Парсеры"
2. Выберите авторизованный Telegram аккаунт
3. Укажите каналы для мониторинга (например: `krymskiye_dela`)
4. Настройте города: Севастополь, Симферополь, Ялта
5. Включите нужные парсеры
6. Нажмите "Сохранить"

### 13. Тестирование бота

1. Найдите вашего бота в Telegram
2. Отправьте `/start`
3. Попробуйте команды: `/events`, `/help`

### 14. Настройка автоматического backup

```bash
# Делаем скрипт исполняемым
chmod +x /opt/cudaCrimea/scripts/backup.sh

# Создаём директорию для бэкапов
mkdir -p /opt/cudaCrimea/backups

# Добавляем в cron
crontab -e
```

Добавьте строку (backup каждый день в 3:00):
```
0 3 * * * /opt/cudaCrimea/scripts/backup.sh >> /var/log/cudacrimea_backup.log 2>&1
```

### 15. Настройка домена (опционально)

#### DNS настройка:

Добавьте A-запись:
```
your-domain.com  →  your-server-ip
```

#### SSL сертификат (Let's Encrypt):

```bash
# Останавливаем nginx временно
cd /opt/cudaCrimea/infra
docker compose stop nginx

# Устанавливаем certbot
sudo apt install -y certbot

# Получаем сертификат
sudo certbot certonly --standalone -d your-domain.com

# Создаём директорию для SSL
mkdir -p /opt/cudaCrimea/infra/ssl

# Копируем сертификаты
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem /opt/cudaCrimea/infra/ssl/
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem /opt/cudaCrimea/infra/ssl/
sudo chmod 644 /opt/cudaCrimea/infra/ssl/*

# Раскомментируем SSL volume в docker-compose.yml
nano /opt/cudaCrimea/infra/docker-compose.yml
# Найдите и раскомментируйте:
# - ./ssl:/etc/nginx/ssl:ro

# Запускаем nginx
docker compose start nginx

# Автообновление сертификатов
sudo crontab -e
# Добавьте:
# 0 2 * * * certbot renew --quiet && cp /etc/letsencrypt/live/your-domain.com/*.pem /opt/cudaCrimea/infra/ssl/ && docker compose -f /opt/cudaCrimea/infra/docker-compose.yml restart nginx
```

## ✅ Проверочный чеклист

После установки проверьте:

- [ ] Все контейнеры запущены: `docker compose ps`
- [ ] API отвечает: `curl http://localhost:8000/health`
- [ ] Админка доступна: `http://your-server-ip/admin/`
- [ ] Бот отвечает в Telegram
- [ ] Парсеры настроены
- [ ] Telegram аккаунт авторизован
- [ ] Backup настроен в cron
- [ ] Firewall включен: `sudo ufw status`
- [ ] Логи без критичных ошибок: `docker compose logs --tail 100`

## 🔄 Последующие обновления

После первоначальной настройки, для обновлений используйте:

```bash
# Простой способ
cd /opt/cudaCrimea
git pull origin master
make deploy

# Или через скрипт
bash scripts/deploy.sh
```

## 📊 Мониторинг

```bash
# Просмотр логов
cd /opt/cudaCrimea/infra
docker compose logs -f

# Конкретный сервис
docker compose logs -f api
docker compose logs -f bot

# Статус сервисов
docker compose ps

# Использование ресурсов
docker stats

# Свободное место
df -h
du -sh /opt/cudaCrimea
```

## 🆘 Troubleshooting

### Контейнеры не запускаются

```bash
# Проверить логи
docker compose logs

# Пересобрать
docker compose down
docker compose build --no-cache
docker compose up -d
```

### "Permission denied" ошибки

```bash
# Исправить права
sudo chown -R $USER:$USER /opt/cudaCrimea
```

### База данных не подключается

```bash
# Проверить что контейнер запущен
docker compose ps db

# Проверить пароль в .env
cat .env | grep DB_PASSWORD

# Проверить подключение
docker compose exec db psql -U postgres -c "SELECT version();"
```

### Nginx не запускается

```bash
# Проверить конфигурацию
docker compose exec nginx nginx -t

# Проверить htpasswd файл
ls -la infra/nginx.htpasswd

# Проверить порты
sudo netstat -tlnp | grep :80
```

## 📞 Получение помощи

Если возникли проблемы:

1. Проверьте логи: `docker compose logs`
2. Проверьте [DEPLOY.md](./DEPLOY.md) секцию Troubleshooting
3. Проверьте [GIT_WORKFLOW.md](./GIT_WORKFLOW.md) для Git проблем
4. Создайте issue с подробным описанием:
   - Что делали
   - Что ожидали
   - Что получили (логи, ошибки)
   - Версия ОС, Docker

## 🎉 Готово!

Поздравляю! Проект развернут и готов к работе.

**Доступ к сервисам:**
- API: `http://your-server-ip:8000`
- Admin: `http://your-server-ip/admin/`
- Telegram Bot: `@your_bot_username`
- Метрики: `http://your-server-ip/metrics`

**Следующие шаги:**
1. Протестируйте бота
2. Настройте парсеры
3. Добавьте события вручную через UGC
4. Мониторьте логи первые дни
5. Настройте мониторинг (опционально)
