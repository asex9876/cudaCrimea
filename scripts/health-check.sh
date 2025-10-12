#!/bin/bash
# ===================================================================
# cudaCrimea - Quick Health Check
# ===================================================================
# Быстрая проверка критичных компонентов
# Exit code: 0 = OK, 1 = Problems found
# Usage: ./scripts/health-check.sh
# ===================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Icons
CHECK="✅"
CROSS="❌"

# Exit code
EXIT_CODE=0

# Project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT/infra"

echo "🔍 Running health check..."
echo ""

# ===================================================================
# 1. Check if containers are running
# ===================================================================
echo "1️⃣ Checking containers..."

REQUIRED_CONTAINERS="api bot worker db redis nginx"
for container in $REQUIRED_CONTAINERS; do
    if docker compose ps $container 2>/dev/null | grep -q "Up"; then
        echo -e "   ${CHECK} $container is running"
    else
        echo -e "   ${CROSS} $container is NOT running!"
        EXIT_CODE=1
    fi
done

echo ""

# ===================================================================
# 2. Check health status
# ===================================================================
echo "2️⃣ Checking health status..."

# DB health
if docker compose exec -T db pg_isready -U postgres &> /dev/null; then
    echo -e "   ${CHECK} Database is healthy"
else
    echo -e "   ${CROSS} Database is NOT healthy!"
    EXIT_CODE=1
fi

# Redis health
if docker compose exec -T redis redis-cli ping 2>/dev/null | grep -q "PONG"; then
    echo -e "   ${CHECK} Redis is healthy"
else
    echo -e "   ${CROSS} Redis is NOT healthy!"
    EXIT_CODE=1
fi

# Nginx health
if docker compose exec -T nginx curl -f -s http://localhost/health > /dev/null 2>&1; then
    echo -e "   ${CHECK} Nginx is healthy"
else
    echo -e "   ${CROSS} Nginx is NOT healthy!"
    EXIT_CODE=1
fi

echo ""

# ===================================================================
# 3. Check critical endpoints
# ===================================================================
echo "3️⃣ Checking endpoints..."

# Admin panel
ADMIN_STATUS=$(docker compose exec -T nginx curl -o /dev/null -s -w "%{http_code}" http://localhost/admin/ 2>/dev/null)
if [ "$ADMIN_STATUS" = "401" ] || [ "$ADMIN_STATUS" = "200" ]; then
    echo -e "   ${CHECK} Admin panel is responding (HTTP $ADMIN_STATUS)"
else
    echo -e "   ${CROSS} Admin panel is NOT responding (HTTP $ADMIN_STATUS)!"
    EXIT_CODE=1
fi

# API health
API_HEALTH=$(docker compose exec -T nginx curl -s http://localhost/api/health 2>/dev/null)
if echo "$API_HEALTH" | grep -q "ok"; then
    echo -e "   ${CHECK} API is responding"
else
    # Try direct connection to API container
    if docker compose exec -T api curl -s http://localhost:8000/ 2>/dev/null | grep -q "Admin"; then
        echo -e "   ${CHECK} API is responding (admin app)"
    else
        echo -e "   ${CROSS} API is NOT responding!"
        EXIT_CODE=1
    fi
fi

echo ""

# ===================================================================
# 4. Check for recent errors
# ===================================================================
echo "4️⃣ Checking for errors..."

for service in api bot worker; do
    ERROR_COUNT=$(docker logs cuda_$service --tail 50 2>&1 | grep -i "error\|exception\|failed" | grep -v "No error" | wc -l)
    if [ "$ERROR_COUNT" -eq 0 ]; then
        echo -e "   ${CHECK} $service: no recent errors"
    else
        echo -e "   ${CROSS} $service: $ERROR_COUNT error(s) in last 50 lines"
        EXIT_CODE=1
    fi
done

echo ""

# ===================================================================
# 5. Check disk space
# ===================================================================
echo "5️⃣ Checking disk space..."

DISK_USAGE=$(df -h . | tail -1 | awk '{print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -lt 80 ]; then
    echo -e "   ${CHECK} Disk usage: ${DISK_USAGE}%"
elif [ "$DISK_USAGE" -lt 90 ]; then
    echo -e "   ⚠️  Disk usage: ${DISK_USAGE}% (getting high)"
else
    echo -e "   ${CROSS} Disk usage: ${DISK_USAGE}% (CRITICAL!)"
    EXIT_CODE=1
fi

echo ""

# ===================================================================
# Summary
# ===================================================================
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✅ All health checks passed!${NC}"
else
    echo -e "${RED}❌ Health check failed! Run 'make diagnose' for details.${NC}"
fi

exit $EXIT_CODE
