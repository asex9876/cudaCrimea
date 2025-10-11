#!/bin/bash

# ==============================================
# cudaCrimea Deployment Script
# ==============================================
# Автоматически обновляет проект на сервере

set -e  # Exit on error

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_DIR="/opt/cudaCrimea"
BRANCH="${1:-master}"  # Default: master, можно передать: ./deploy.sh main

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

# Check if running on server
if [ ! -d "$PROJECT_DIR" ]; then
    log_error "Project directory not found: $PROJECT_DIR"
    log_info "Are you running this on the server?"
    exit 1
fi

cd "$PROJECT_DIR"

log_info "Starting deployment of cudaCrimea..."
log_info "Branch: $BRANCH"
log_info "Project: $PROJECT_DIR"
echo ""

# Step 1: Git pull
log_step "1/7: Pulling latest changes from git..."
git fetch origin
BEFORE_HASH=$(git rev-parse HEAD)
git pull origin "$BRANCH"
AFTER_HASH=$(git rev-parse HEAD)

if [ "$BEFORE_HASH" = "$AFTER_HASH" ]; then
    log_warn "No new changes detected. Already up to date."
    read -p "Continue deployment anyway? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Deployment cancelled"
        exit 0
    fi
else
    log_info "Updated from $BEFORE_HASH to $AFTER_HASH"
    echo "Recent changes:"
    git log --oneline --decorate --graph -5
fi

echo ""

# Step 2: Check .env file
log_step "2/7: Checking environment configuration..."
if [ ! -f ".env" ]; then
    log_error ".env file not found!"
    log_info "Copy from .env.example and configure"
    exit 1
fi
log_info ".env file exists ✓"

# Step 3: Stop services
log_step "3/7: Stopping services..."
cd infra
docker compose stop api bot worker
log_info "Services stopped ✓"

# Step 4: Build images
log_step "4/7: Building Docker images..."
docker compose build --no-cache api bot worker
log_info "Images built ✓"

# Step 5: Start services
log_step "5/7: Starting services..."
docker compose up -d
log_info "Services started ✓"

# Step 6: Wait for services to be healthy
log_step "6/7: Waiting for services to be healthy..."
sleep 10

RETRIES=0
MAX_RETRIES=30
while [ $RETRIES -lt $MAX_RETRIES ]; do
    if docker compose ps | grep -q "healthy"; then
        log_info "Services are healthy ✓"
        break
    fi
    echo -n "."
    sleep 2
    RETRIES=$((RETRIES + 1))
done

if [ $RETRIES -eq $MAX_RETRIES ]; then
    log_warn "Services not healthy after ${MAX_RETRIES} retries"
    log_info "Check logs: docker compose logs"
fi

echo ""

# Step 7: Run migrations
log_step "7/7: Running database migrations..."
docker compose exec -T api alembic upgrade head
log_info "Migrations applied ✓"

echo ""

# Show status
log_info "Deployment completed!"
echo ""
log_info "Service status:"
docker compose ps

echo ""
log_info "Recent logs:"
docker compose logs --tail 20

echo ""
log_info "🎉 Deployment successful!"
log_info "API: http://your-domain:8000"
log_info "Admin: http://your-domain/admin/"
log_info "Bot: Check in Telegram"

echo ""
log_warn "Don't forget to:"
echo "  1. Check logs: make logs"
echo "  2. Test bot in Telegram"
echo "  3. Check admin panel"
echo "  4. Monitor for errors"

exit 0
