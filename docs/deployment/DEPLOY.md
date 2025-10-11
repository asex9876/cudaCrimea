# 🚀 Инструкция по деплою CudaCrimea на сервер Ubuntu

## 📋 Подготовка сервера

### 1. Требования к серверу

**Минимальная конфигурация** (для старта):
- CPU: 2 vCPU
- RAM: 4 GB
- Диск: 50 GB SSD
- ОС: Ubuntu 20.04 / 22.04 LTS

**Рекомендуемая конфигурация** (для 5000+ пользователей):
- CPU: 4 vCPU
- RAM: 8 GB
- Диск: 100 GB SSD
- ОС: Ubuntu 22.04 LTS

### 2. Подключение к серверу

```bash
ssh root@your_server_ip
```

### 3. Установка необходимого ПО

```bash
# Обновление системы
apt update && apt upgrade -y

# Установка Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Установка Docker Compose
apt install -y docker-compose

# Установка git
apt install -y git

# Установка дополнительных утилит
apt install -y htop nano curl wget apache2-utils

# Проверка установки
docker --version
docker-compose --version
git --version
```

### 4. Создание пользователя для приложения

```bash
# Создание пользователя
useradd -m -s /bin/bash cudaapp
usermod -aG docker cudaapp

# Переключение на пользователя
su - cudaapp
```

---

## 📦 Установка проекта

### 1. Клонирование репозитория

```bash
# Клонируйте свой репозиторий (замените URL на свой)
cd ~
git clone https://github.com/ваш-username/cudaCrimea.git
cd cudaCrimea
```

**Если репозитория ещё нет**, создайте его на GitHub/GitLab и залейте код:

```bash
# На вашем компьютере (локально)
cd "C:\Users\sanve\OneDrive\Рабочий стол\cudaCrimea"
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/ваш-username/cudaCrimea.git
git push -u origin main
```

### 2. Настройка переменных окружения

```bash
# Копирование шаблона .env
cp .env.example .env

# Редактирование .env
nano .env
```

**Обязательно измените следующие параметры:**

```bash
# Runtime
ENV=production  # ВАЖНО: ставим production!

# Telegram (ваши реальные данные)
BOT_TOKEN=ваш_токен_бота
TELEGRAM_API_ID=ваш_api_id
TELEGRAM_API_HASH=ваш_api_hash

# Database (придумайте сложный пароль!)
DATABASE_URL=postgresql+asyncpg://postgres:СЛОЖНЫЙ_ПАРОЛЬ@db:5432/cudacrimea
DB_PASSWORD=СЛОЖНЫЙ_ПАРОЛЬ  # Тот же самый пароль!

# Admin (придумайте сложные логин и пароль!)
ADMIN_USER=ваш_логин
ADMIN_PASSWORD=ваш_сложный_пароль
ADMIN_SECRET=случайная_строка_минимум_32_символа

# AI (ваши API ключи)
AI_MEDIATOR_API_KEY=ваш_ключ
```

**Сохраните файл:** `Ctrl+O`, `Enter`, `Ctrl+X`

### 3. Генерация htpasswd для nginx

```bash
cd infra

# Создание файла с паролем для админки nginx
# Замените admin и password на свои значения!
htpasswd -c nginx.htpasswd admin
# Введите пароль дважды
```

### 4. Деплой приложения

```bash
# Запуск скрипта деплоя
cd ~/cudaCrimea/infra
chmod +x deploy.sh update.sh backup.sh
./deploy.sh
```

Скрипт автоматически:
- Проверит .env файл
- Создаст необходимые директории
- Соберёт Docker образы
- Запустит все контейнеры
- Применит миграции базы данных

---

## 🌐 Проверка работы

### 1. Проверка контейнеров

```bash
cd ~/cudaCrimea/infra
docker-compose -f docker-compose.prod.yml ps
```

Все контейнеры должны быть в статусе `Up`.

### 2. Проверка логов

```bash
# Логи всех сервисов
docker-compose -f docker-compose.prod.yml logs -f

# Логи бота
docker logs cuda_bot -f

# Логи API
docker logs cuda_api -f

# Для выхода: Ctrl+C
```

### 3. Проверка доступности

Откройте в браузере:
- **API**: `http://ваш_ip_адрес/api/`
- **Админка**: `http://ваш_ip_адрес/admin/` (логин: admin, пароль: тот что вы создали)

---

## 🔄 Рабочий процесс разработки

### На вашем компьютере (локально):

```bash
# 1. Вы работаете с кодом как обычно
# 2. Я помогаю вам вносить изменения
# 3. Когда всё готово, сохраняете в git:

git add .
git commit -m "Описание изменений"
git push origin main
```

### На сервере:

```bash
# Обновление проекта на сервере
cd ~/cudaCrimea/infra
./update.sh
```

Скрипт автоматически:
- Получит последние изменения из git
- Перезапустит контейнеры
- Применит миграции (если есть)

**Весь процесс занимает 10-20 секунд!**

---

## 🔒 SSL сертификат (HTTPS)

### Установка бесплатного SSL от Let's Encrypt

```bash
# Установка certbot
sudo apt install -y certbot

# Временная остановка nginx для получения сертификата
cd ~/cudaCrimea/infra
docker-compose -f docker-compose.prod.yml stop nginx

# Получение сертификата (замените на ваш домен!)
sudo certbot certonly --standalone -d your-domain.com -d www.your-domain.com

# Копирование сертификатов в проект
sudo mkdir -p ~/cudaCrimea/infra/ssl
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem ~/cudaCrimea/infra/ssl/
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem ~/cudaCrimea/infra/ssl/
sudo chown -R cudaapp:cudaapp ~/cudaCrimea/infra/ssl

# Редактирование nginx конфига
nano ~/cudaCrimea/infra/nginx.prod.conf
# Раскомментируйте блок HTTPS server и замените your-domain.com на ваш домен

# Добавление volume для SSL в docker-compose.prod.yml
nano ~/cudaCrimea/infra/docker-compose.prod.yml
# Раскомментируйте строку: # - ./ssl:/etc/nginx/ssl:ro

# Перезапуск nginx
docker-compose -f docker-compose.prod.yml up -d nginx
```

### Автообновление сертификата

```bash
# Добавление задачи в cron
sudo crontab -e

# Добавьте эту строку в конец файла:
0 3 * * * certbot renew --quiet && cp /etc/letsencrypt/live/your-domain.com/*.pem /home/cudaapp/cudaCrimea/infra/ssl/ && docker restart cuda_nginx
```

---

## 💾 Резервное копирование

### Создание бэкапа вручную

```bash
cd ~/cudaCrimea/infra
./backup.sh
```

Бэкап сохранится в `~/cudaCrimea/infra/backups/`

### Автоматический бэкап (каждый день в 2:00)

```bash
crontab -e

# Добавьте эту строку:
0 2 * * * /home/cudaapp/cudaCrimea/infra/backup.sh
```

### Восстановление из бэкапа

```bash
cd ~/cudaCrimea/infra

# Найдите нужный бэкап
ls -lh backups/

# Восстановите (замените имя файла на нужное)
gunzip -c backups/backup_20250105_020000.sql.gz | docker exec -i cuda_db psql -U postgres cudacrimea
```

---

## 📊 Мониторинг

### Полезные команды

```bash
# Статус контейнеров
docker-compose -f docker-compose.prod.yml ps

# Использование ресурсов
docker stats

# Системные ресурсы
htop

# Размер дисков
df -h

# Логи последних 100 строк
docker logs cuda_bot --tail 100

# Перезапуск отдельного сервиса
docker restart cuda_bot

# Перезапуск всех сервисов
cd ~/cudaCrimea/infra
docker-compose -f docker-compose.prod.yml restart
```

### Мониторинг логов в реальном времени

```bash
# Все сервисы
docker-compose -f docker-compose.prod.yml logs -f

# Только бот
docker logs cuda_bot -f

# Только API
docker logs cuda_api -f

# Только база данных
docker logs cuda_db -f
```

---

## 🆘 Решение проблем

### Контейнер не запускается

```bash
# Проверить логи
docker logs cuda_bot

# Проверить конфигурацию
docker-compose -f docker-compose.prod.yml config

# Пересобрать образ
docker-compose -f docker-compose.prod.yml build --no-cache cuda_bot
docker-compose -f docker-compose.prod.yml up -d
```

### База данных не доступна

```bash
# Проверить статус
docker ps -a | grep cuda_db

# Перезапустить
docker restart cuda_db

# Посмотреть логи
docker logs cuda_db
```

### Закончилось место на диске

```bash
# Очистка старых Docker образов
docker system prune -a

# Очистка старых бэкапов (старше 30 дней)
find ~/cudaCrimea/infra/backups -name "*.sql.gz" -mtime +30 -delete

# Проверка размера
du -sh ~/cudaCrimea/app/admin/static/uploads/
```

### Полный перезапуск

```bash
cd ~/cudaCrimea/infra
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml up -d --build
```

---

## 🎯 Чек-лист после деплоя

- [ ] Все контейнеры запущены (`docker-compose ps`)
- [ ] Бот отвечает в Telegram
- [ ] Админка открывается в браузере
- [ ] API отвечает на запросы
- [ ] Логи не показывают ошибок
- [ ] SSL сертификат установлен (если используется домен)
- [ ] Автоматический бэкап настроен
- [ ] Пароли в .env сменены на сложные
- [ ] htpasswd для nginx настроен

---

## 📞 Контакты и поддержка

Если возникли проблемы:

1. Проверьте логи: `docker-compose logs -f`
2. Посмотрите этот документ ещё раз
3. Проверьте .env файл
4. Убедитесь что все контейнеры запущены

**Важные файлы:**
- `.env` - настройки окружения
- `infra/docker-compose.prod.yml` - конфигурация Docker
- `infra/nginx.prod.conf` - конфигурация nginx
- `infra/deploy.sh` - скрипт первого деплоя
- `infra/update.sh` - скрипт обновления
- `infra/backup.sh` - скрипт бэкапа

---

## 🚀 Готово!

Ваш проект теперь работает на сервере!

**Процесс обновления в будущем:**
1. Вы работаете локально на своём компьютере
2. Я помогаю вам с изменениями
3. Вы делаете `git push`
4. На сервере запускаете `./update.sh`
5. Готово! (10-20 секунд)
