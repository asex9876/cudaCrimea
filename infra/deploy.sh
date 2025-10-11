#!/bin/bash
# ========================================
# Скрипт первого деплоя на сервер
# ========================================
set -e  # Остановка при ошибке

echo "🚀 Деплой CudaCrimea на сервер..."

# Проверка что .env файл существует
if [ ! -f "../.env" ]; then
    echo "❌ Ошибка: Файл .env не найден!"
    echo "Скопируйте .env.example в .env и заполните настройки:"
    echo "  cp .env.example .env"
    echo "  nano .env"
    exit 1
fi

# Проверка что в .env заполнены критичные поля
if grep -q "CHANGE_THIS_PASSWORD" ../.env; then
    echo "❌ Ошибка: В файле .env найдены незаполненные поля (CHANGE_THIS_PASSWORD)!"
    echo "Отредактируйте .env и замените все CHANGE_THIS_PASSWORD на реальные пароли."
    exit 1
fi

# Создание папки для загруженных файлов
echo "📁 Создание директорий..."
mkdir -p ../app/admin/static/uploads
mkdir -p ./backups
mkdir -p ./ssl

# Проверка что htpasswd файл существует
if [ ! -f "./nginx.htpasswd" ]; then
    echo "⚠️  Файл nginx.htpasswd не найден!"
    echo "Создаём новый файл с логином 'admin' и паролем 'admin123'"
    echo "ВАЖНО: Измените пароль после деплоя!"

    # Проверка что htpasswd установлен
    if ! command -v htpasswd &> /dev/null; then
        echo "Устанавливаем apache2-utils для создания htpasswd..."
        sudo apt-get update
        sudo apt-get install -y apache2-utils
    fi

    htpasswd -cb nginx.htpasswd admin admin123
fi

# Остановка старых контейнеров (если есть)
echo "🛑 Остановка старых контейнеров..."
docker-compose -f docker-compose.prod.yml down || true

# Сборка и запуск
echo "🔨 Сборка Docker образов..."
docker-compose -f docker-compose.prod.yml build

echo "🚢 Запуск контейнеров..."
docker-compose -f docker-compose.prod.yml up -d

# Ожидание запуска базы данных
echo "⏳ Ожидание запуска базы данных..."
sleep 10

# Применение миграций (если есть)
echo "🗄️  Применение миграций базы данных..."
docker-compose -f docker-compose.prod.yml exec -T api alembic upgrade head || echo "⚠️  Миграции не применены (возможно их нет)"

# Проверка статуса
echo "✅ Проверка статуса контейнеров..."
docker-compose -f docker-compose.prod.yml ps

echo ""
echo "✨ Деплой завершён!"
echo ""
echo "📋 Полезные команды:"
echo "  Логи всех сервисов:    docker-compose -f docker-compose.prod.yml logs -f"
echo "  Логи бота:             docker logs cuda_bot -f"
echo "  Логи API:              docker logs cuda_api -f"
echo "  Перезапуск:            docker-compose -f docker-compose.prod.yml restart"
echo "  Остановка:             docker-compose -f docker-compose.prod.yml down"
echo ""
echo "🌐 Сервисы доступны по адресам:"
echo "  Админка: http://$(hostname -I | awk '{print $1}')/admin/"
echo "  API:     http://$(hostname -I | awk '{print $1}')/api/"
echo ""
echo "🔒 Логин для админки: admin / admin123 (СМЕНИТЕ ПАРОЛЬ!)"
echo ""
