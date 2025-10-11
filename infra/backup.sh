#!/bin/bash
# ========================================
# Скрипт резервного копирования базы данных
# ========================================
set -e

BACKUP_DIR="./backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/backup_$DATE.sql"

echo "💾 Создание бэкапа базы данных..."

# Создание директории для бэкапов
mkdir -p $BACKUP_DIR

# Создание дампа базы данных
docker exec cuda_db pg_dump -U postgres cudacrimea > $BACKUP_FILE

# Сжатие бэкапа
gzip $BACKUP_FILE

echo "✅ Бэкап создан: ${BACKUP_FILE}.gz"

# Удаление бэкапов старше 7 дней
echo "🧹 Удаление старых бэкапов (старше 7 дней)..."
find $BACKUP_DIR -name "backup_*.sql.gz" -mtime +7 -delete

echo "✨ Готово!"
echo ""
echo "📋 Для восстановления из бэкапа используйте:"
echo "  gunzip -c ${BACKUP_FILE}.gz | docker exec -i cuda_db psql -U postgres cudacrimea"
echo ""
