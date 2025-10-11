#!/bin/bash
# ========================================
# Скрипт обновления проекта на сервере
# ========================================
set -e  # Остановка при ошибке

echo "🔄 Обновление CudaCrimea..."

# Получение последних изменений из git
echo "📥 Получение изменений из git..."
cd ..
git pull origin main || git pull origin master

# Возврат в директорию infra
cd infra

# Перезапуск контейнеров
echo "🔄 Перезапуск контейнеров..."
docker compose -f docker-compose.prod.yml restart

# Применение миграций (если есть новые)
echo "🗄️  Проверка миграций базы данных..."
docker compose -f docker-compose.prod.yml exec -T api alembic upgrade head || echo "⚠️  Миграции не применены"

# Проверка статуса
echo "✅ Проверка статуса..."
docker compose -f docker-compose.prod.yml ps

echo ""
echo "✨ Обновление завершено!"
echo ""
echo "📋 Логи можно посмотреть командой:"
echo "  docker compose -f docker-compose.prod.yml logs -f"
echo ""
