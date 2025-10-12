#!/bin/bash
# ===================================================================
# cudaCrimea - Comprehensive Diagnostics Script
# ===================================================================
# Проверяет все компоненты системы и выявляет проблемы
# Usage: ./scripts/diagnostics.sh
# ===================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Icons
CHECK="✅"
CROSS="❌"
WARN="⚠️"
INFO="ℹ️"

# Counters
TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0
WARNINGS=0

# Project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   cudaCrimea Diagnostics v1.0${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Helper functions
log_info() {
    echo -e "${INFO} ${BLUE}$1${NC}"
}

log_success() {
    echo -e "${CHECK} ${GREEN}$1${NC}"
    ((PASSED_CHECKS++))
    ((TOTAL_CHECKS++))
}

log_error() {
    echo -e "${CROSS} ${RED}$1${NC}"
    ((FAILED_CHECKS++))
    ((TOTAL_CHECKS++))
}

log_warn() {
    echo -e "${WARN} ${YELLOW}$1${NC}"
    ((WARNINGS++))
    ((TOTAL_CHECKS++))
}

section() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
}

# ===================================================================
# 1. System Information
# ===================================================================
section "1. System Information"

log_info "OS: $(uname -s) $(uname -r)"
log_info "Hostname: $(hostname)"
log_info "User: $(whoami)"
log_info "Date: $(date)"
log_info "Project root: $PROJECT_ROOT"

# ===================================================================
# 2. Docker Installation
# ===================================================================
section "2. Docker Installation"

if command -v docker &> /dev/null; then
    DOCKER_VERSION=$(docker --version)
    log_success "Docker installed: $DOCKER_VERSION"
else
    log_error "Docker NOT installed!"
fi

if docker compose version &> /dev/null; then
    COMPOSE_VERSION=$(docker compose version)
    log_success "Docker Compose V2 installed: $COMPOSE_VERSION"
elif command -v docker-compose &> /dev/null; then
    COMPOSE_VERSION=$(docker-compose --version)
    log_warn "Docker Compose V1 installed (deprecated): $COMPOSE_VERSION"
else
    log_error "Docker Compose NOT installed!"
fi

# ===================================================================
# 3. Docker Containers Status
# ===================================================================
section "3. Docker Containers Status"

# Determine which compose file is used
if [ -f "infra/docker-compose.prod.yml" ]; then
    COMPOSE_FILE="infra/docker-compose.prod.yml"
    log_info "Using production compose file"
elif [ -f "infra/docker-compose.yml" ]; then
    COMPOSE_FILE="infra/docker-compose.yml"
    log_info "Using development compose file"
else
    log_error "No docker-compose file found!"
    COMPOSE_FILE=""
fi

if [ -n "$COMPOSE_FILE" ]; then
    cd infra

    # Check if containers are running
    CONTAINERS=$(docker compose -f $(basename $COMPOSE_FILE) ps -q 2>/dev/null | wc -l)

    if [ "$CONTAINERS" -gt 0 ]; then
        log_success "Found $CONTAINERS running containers"

        # Check individual services
        for service in api bot worker db redis nginx; do
            if docker compose -f $(basename $COMPOSE_FILE) ps $service 2>/dev/null | grep -q "Up"; then
                STATUS=$(docker compose -f $(basename $COMPOSE_FILE) ps $service | grep $service | awk '{print $4, $5, $6}')

                if echo "$STATUS" | grep -q "healthy"; then
                    log_success "$service: Running (healthy)"
                elif echo "$STATUS" | grep -q "unhealthy"; then
                    log_error "$service: Running but UNHEALTHY"
                else
                    log_warn "$service: Running (no health check)"
                fi
            else
                log_error "$service: NOT running"
            fi
        done
    else
        log_error "No containers are running!"
    fi

    cd ..
fi

# ===================================================================
# 4. Docker Resources
# ===================================================================
section "4. Docker Resources"

# Disk usage
DISK_USAGE=$(docker system df 2>/dev/null || echo "N/A")
log_info "Docker disk usage:"
echo "$DISK_USAGE" | tail -n +2

# Container stats (non-streaming, single snapshot)
log_info "Container resource usage:"
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" 2>/dev/null | head -10 || log_warn "Could not get container stats"

# ===================================================================
# 5. Network Connectivity
# ===================================================================
section "5. Network Connectivity"

cd infra 2>/dev/null || cd .

# Test connectivity between services
if docker compose ps api &> /dev/null; then
    # API -> DB
    if docker compose exec -T api timeout 5 nc -z db 5432 2>/dev/null; then
        log_success "API can reach DB (PostgreSQL)"
    else
        log_error "API CANNOT reach DB!"
    fi

    # API -> Redis
    if docker compose exec -T api timeout 5 nc -z redis 6379 2>/dev/null; then
        log_success "API can reach Redis"
    else
        log_error "API CANNOT reach Redis!"
    fi
fi

cd - > /dev/null

# ===================================================================
# 6. Database Status
# ===================================================================
section "6. Database Status"

cd infra 2>/dev/null || cd .

if docker compose ps db &> /dev/null; then
    # Check if DB is accepting connections
    if docker compose exec -T db pg_isready -U postgres &> /dev/null; then
        log_success "PostgreSQL is accepting connections"

        # Count tables
        TABLE_COUNT=$(docker compose exec -T db psql -U postgres -d cudacrimea -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';" 2>/dev/null | tr -d ' ')
        if [ -n "$TABLE_COUNT" ] && [ "$TABLE_COUNT" -gt 0 ]; then
            log_success "Database has $TABLE_COUNT tables"
        else
            log_warn "Database exists but no tables found (migrations not applied?)"
        fi

        # Count events
        EVENT_COUNT=$(docker compose exec -T db psql -U postgres -d cudacrimea -t -c "SELECT COUNT(*) FROM events;" 2>/dev/null | tr -d ' ')
        if [ -n "$EVENT_COUNT" ]; then
            log_info "Total events in database: $EVENT_COUNT"
        fi
    else
        log_error "PostgreSQL is NOT accepting connections!"
    fi
fi

cd - > /dev/null

# ===================================================================
# 7. Redis Status
# ===================================================================
section "7. Redis Status"

cd infra 2>/dev/null || cd .

if docker compose ps redis &> /dev/null; then
    # Test Redis connection
    if docker compose exec -T redis redis-cli ping 2>/dev/null | grep -q "PONG"; then
        log_success "Redis is responding"

        # Get memory info
        REDIS_MEM=$(docker compose exec -T redis redis-cli info memory 2>/dev/null | grep "used_memory_human" | cut -d: -f2 | tr -d '\r')
        log_info "Redis memory usage: $REDIS_MEM"

        # Count keys
        KEY_COUNT=$(docker compose exec -T redis redis-cli DBSIZE 2>/dev/null | awk '{print $2}')
        log_info "Redis keys: $KEY_COUNT"
    else
        log_error "Redis is NOT responding!"
    fi
fi

cd - > /dev/null

# ===================================================================
# 8. API/Admin Endpoints
# ===================================================================
section "8. API/Admin Endpoints"

cd infra 2>/dev/null || cd .

if docker compose ps nginx &> /dev/null; then
    # Test nginx health
    if docker compose exec -T nginx curl -f -s http://localhost/health > /dev/null 2>&1; then
        log_success "Nginx health check passed"
    else
        log_error "Nginx health check FAILED!"
    fi

    # Test admin panel
    ADMIN_STATUS=$(docker compose exec -T nginx curl -o /dev/null -s -w "%{http_code}" http://localhost/admin/ 2>/dev/null)
    if [ "$ADMIN_STATUS" = "401" ]; then
        log_success "Admin panel responding (requires auth)"
    elif [ "$ADMIN_STATUS" = "200" ]; then
        log_success "Admin panel responding (no auth required)"
    else
        log_error "Admin panel NOT responding (HTTP $ADMIN_STATUS)"
    fi

    # Test API
    API_HEALTH=$(docker compose exec -T nginx curl -s http://localhost/api/health 2>/dev/null)
    if echo "$API_HEALTH" | grep -q "ok"; then
        log_success "API health endpoint responding"
    else
        log_warn "API health endpoint not found or not responding"
    fi
fi

cd - > /dev/null

# ===================================================================
# 9. Configuration Files
# ===================================================================
section "9. Configuration Files"

# Check .env file
if [ -f ".env" ]; then
    log_success ".env file exists"

    # Check critical variables
    if grep -q "^BOT_TOKEN=" .env && ! grep -q "^BOT_TOKEN=$" .env; then
        log_success "BOT_TOKEN is set"
    else
        log_error "BOT_TOKEN is NOT set in .env!"
    fi

    if grep -q "^DATABASE_URL=" .env && ! grep -q "^DATABASE_URL=$" .env; then
        log_success "DATABASE_URL is set"
    else
        log_error "DATABASE_URL is NOT set in .env!"
    fi

    if grep -q "^DB_PASSWORD=" .env && ! grep -q "^DB_PASSWORD=$" .env; then
        log_success "DB_PASSWORD is set"
    else
        log_warn "DB_PASSWORD is NOT set in .env"
    fi
else
    log_error ".env file NOT found!"
fi

# Check nginx htpasswd
if [ -f "infra/nginx.htpasswd" ]; then
    log_success "nginx.htpasswd exists"
else
    log_warn "nginx.htpasswd NOT found (admin won't be protected)"
fi

# ===================================================================
# 10. File Permissions & Volumes
# ===================================================================
section "10. File Permissions & Volumes"

# Check uploads directory
if [ -d "app/admin/uploads" ]; then
    UPLOAD_COUNT=$(ls -1 app/admin/uploads 2>/dev/null | wc -l)
    log_success "Uploads directory exists ($UPLOAD_COUNT files)"
else
    log_warn "Uploads directory does not exist"
fi

# Check if code is mounted in containers
cd infra 2>/dev/null || cd .
if docker compose ps api &> /dev/null; then
    MOUNT_CHECK=$(docker compose exec -T api ls /app/app/admin/main.py 2>/dev/null)
    if [ -n "$MOUNT_CHECK" ]; then
        log_success "Code is mounted in API container"
    else
        log_error "Code is NOT mounted in API container!"
    fi
fi
cd - > /dev/null

# ===================================================================
# 11. Recent Errors in Logs
# ===================================================================
section "11. Recent Errors in Logs (Last 50 lines)"

cd infra 2>/dev/null || cd .

for service in api bot worker; do
    if docker compose ps $service &> /dev/null; then
        ERROR_COUNT=$(docker logs $service --tail 50 2>&1 | grep -i "error\|exception\|failed\|traceback" | wc -l)
        if [ "$ERROR_COUNT" -eq 0 ]; then
            log_success "$service: No recent errors"
        elif [ "$ERROR_COUNT" -lt 5 ]; then
            log_warn "$service: $ERROR_COUNT error(s) in last 50 lines"
        else
            log_error "$service: $ERROR_COUNT errors in last 50 lines!"
        fi
    fi
done

cd - > /dev/null

# ===================================================================
# 12. Disk Space
# ===================================================================
section "12. Disk Space"

DISK_USAGE=$(df -h . | tail -1 | awk '{print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -lt 80 ]; then
    log_success "Disk usage: ${DISK_USAGE}%"
elif [ "$DISK_USAGE" -lt 90 ]; then
    log_warn "Disk usage: ${DISK_USAGE}% (getting high)"
else
    log_error "Disk usage: ${DISK_USAGE}% (CRITICAL!)"
fi

# ===================================================================
# Summary
# ===================================================================
section "Summary"

echo ""
echo -e "${BLUE}Total checks:${NC} $TOTAL_CHECKS"
echo -e "${GREEN}Passed:${NC} $PASSED_CHECKS"
echo -e "${YELLOW}Warnings:${NC} $WARNINGS"
echo -e "${RED}Failed:${NC} $FAILED_CHECKS"
echo ""

if [ "$FAILED_CHECKS" -eq 0 ] && [ "$WARNINGS" -eq 0 ]; then
    echo -e "${CHECK} ${GREEN}All systems operational!${NC}"
    exit 0
elif [ "$FAILED_CHECKS" -eq 0 ]; then
    echo -e "${WARN} ${YELLOW}System operational with warnings${NC}"
    exit 0
else
    echo -e "${CROSS} ${RED}Critical issues found! Please review above.${NC}"
    exit 1
fi
