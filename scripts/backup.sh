#!/bin/bash

# ==============================================
# cudaCrimea Database Backup Script
# ==============================================

set -e  # Exit on error

# Configuration
BACKUP_DIR="/opt/cudaCrimea/backups"
CONTAINER_NAME="cuda_db"
DB_NAME="cudacrimea"
DB_USER="postgres"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/backup_$TIMESTAMP.sql"
RETENTION_DAYS=7

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Check if container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    log_error "Container $CONTAINER_NAME is not running!"
    exit 1
fi

log_info "Starting database backup..."

# Create backup
if docker exec "$CONTAINER_NAME" pg_dump -U "$DB_USER" "$DB_NAME" > "$BACKUP_FILE"; then
    log_info "Backup created: $BACKUP_FILE"
else
    log_error "Failed to create backup!"
    exit 1
fi

# Compress backup
log_info "Compressing backup..."
if gzip "$BACKUP_FILE"; then
    log_info "Backup compressed: ${BACKUP_FILE}.gz"
    BACKUP_FILE="${BACKUP_FILE}.gz"
else
    log_error "Failed to compress backup!"
    exit 1
fi

# Calculate backup size
BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
log_info "Backup size: $BACKUP_SIZE"

# Remove old backups
log_info "Removing backups older than $RETENTION_DAYS days..."
DELETED_COUNT=$(find "$BACKUP_DIR" -name "backup_*.sql.gz" -mtime +$RETENTION_DAYS -delete -print | wc -l)
if [ "$DELETED_COUNT" -gt 0 ]; then
    log_info "Deleted $DELETED_COUNT old backup(s)"
else
    log_info "No old backups to delete"
fi

# List recent backups
log_info "Recent backups:"
ls -lh "$BACKUP_DIR"/backup_*.sql.gz | tail -5

log_info "Backup completed successfully!"

# Optional: Upload to remote storage (uncomment if needed)
# if [ -f /opt/cudaCrimea/scripts/upload_backup.sh ]; then
#     log_info "Uploading backup to remote storage..."
#     /opt/cudaCrimea/scripts/upload_backup.sh "$BACKUP_FILE"
# fi

exit 0
