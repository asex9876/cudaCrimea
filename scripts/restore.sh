#!/bin/bash

# ==============================================
# cudaCrimea Database Restore Script
# ==============================================

set -e  # Exit on error

# Configuration
BACKUP_DIR="/opt/cudaCrimea/backups"
CONTAINER_NAME="cuda_db"
DB_NAME="cudacrimea"
DB_USER="postgres"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

# Check if backup file is provided
if [ -z "$1" ]; then
    log_error "Usage: $0 <backup_file>"
    log_info "Available backups:"
    ls -lh "$BACKUP_DIR"/backup_*.sql.gz 2>/dev/null || echo "No backups found"
    exit 1
fi

BACKUP_FILE="$1"

# Check if backup file exists
if [ ! -f "$BACKUP_FILE" ]; then
    log_error "Backup file not found: $BACKUP_FILE"
    exit 1
fi

log_info "Backup file: $BACKUP_FILE"
log_info "Backup size: $(du -h "$BACKUP_FILE" | cut -f1)"

# Confirmation
log_warn "⚠️  WARNING: This will replace the current database with the backup!"
read -p "Are you sure you want to continue? (yes/no): " -r
echo
if [[ ! $REPLY =~ ^[Yy]es$ ]]; then
    log_info "Restore cancelled"
    exit 0
fi

# Check if container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    log_error "Container $CONTAINER_NAME is not running!"
    exit 1
fi

log_step "1/5: Stopping dependent services..."
cd /opt/cudaCrimea/infra
docker compose stop api bot worker || true
log_info "Services stopped"

log_step "2/5: Creating safety backup of current database..."
SAFETY_BACKUP="/tmp/safety_backup_$(date +%Y%m%d_%H%M%S).sql"
if docker exec "$CONTAINER_NAME" pg_dump -U "$DB_USER" "$DB_NAME" > "$SAFETY_BACKUP" 2>/dev/null; then
    log_info "Safety backup created: $SAFETY_BACKUP"
else
    log_warn "Could not create safety backup (database might be empty)"
fi

log_step "3/5: Dropping existing database..."
docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -c "DROP DATABASE IF EXISTS $DB_NAME;" || true
log_info "Database dropped"

log_step "4/5: Creating new database..."
docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -c "CREATE DATABASE $DB_NAME;"
log_info "Database created"

log_step "5/5: Restoring backup..."
if [[ "$BACKUP_FILE" == *.gz ]]; then
    log_info "Decompressing and restoring..."
    gunzip -c "$BACKUP_FILE" | docker exec -i "$CONTAINER_NAME" psql -U "$DB_USER" "$DB_NAME"
else
    log_info "Restoring..."
    cat "$BACKUP_FILE" | docker exec -i "$CONTAINER_NAME" psql -U "$DB_USER" "$DB_NAME"
fi
log_info "Backup restored"

log_step "Starting services..."
docker compose start api bot worker
log_info "Services started"

# Wait for services to be healthy
log_info "Waiting for services to be healthy..."
sleep 5

# Check service health
if docker compose ps | grep -q "healthy"; then
    log_info "✅ Restore completed successfully!"
else
    log_warn "Services are starting, check status with: docker compose ps"
fi

log_info "Safety backup is available at: $SAFETY_BACKUP"
log_info "You can delete it manually if everything works correctly"

exit 0
