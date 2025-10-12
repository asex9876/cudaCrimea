#!/bin/bash
# ===================================================================
# cudaCrimea - Log Collection Script
# ===================================================================
# Собирает все логи и системную информацию в один файл
# Usage: ./scripts/collect-logs.sh [output_file]
# ===================================================================

set -e

# Project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# Output file
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_FILE="${1:-logs_${TIMESTAMP}.txt}"

echo "Collecting logs to: $OUTPUT_FILE"
echo "This may take a minute..."
echo ""

# Start collection
{
    echo "========================================"
    echo "   cudaCrimea Log Collection"
    echo "   Generated: $(date)"
    echo "========================================"
    echo ""

    # ===================================================================
    # 1. System Information
    # ===================================================================
    echo "========================================"
    echo "1. SYSTEM INFORMATION"
    echo "========================================"
    echo ""
    echo "OS: $(uname -a)"
    echo "Hostname: $(hostname)"
    echo "User: $(whoami)"
    echo "Date: $(date)"
    echo "Uptime: $(uptime)"
    echo ""

    # ===================================================================
    # 2. Docker Information
    # ===================================================================
    echo "========================================"
    echo "2. DOCKER INFORMATION"
    echo "========================================"
    echo ""
    echo "Docker version:"
    docker --version 2>&1
    echo ""
    echo "Docker Compose version:"
    docker compose version 2>&1 || docker-compose --version 2>&1
    echo ""
    echo "Docker info:"
    docker info 2>&1 | head -30
    echo ""

    # ===================================================================
    # 3. Container Status
    # ===================================================================
    echo "========================================"
    echo "3. CONTAINER STATUS"
    echo "========================================"
    echo ""

    cd infra 2>/dev/null || cd .

    echo "Docker Compose PS:"
    docker compose ps 2>&1 || echo "Could not get container status"
    echo ""

    echo "Docker PS (all containers):"
    docker ps -a 2>&1
    echo ""

    echo "Container Stats (snapshot):"
    docker stats --no-stream 2>&1 || echo "Could not get stats"
    echo ""

    # ===================================================================
    # 4. Container Inspect
    # ===================================================================
    echo "========================================"
    echo "4. CONTAINER DETAILS"
    echo "========================================"
    echo ""

    for container in cuda_api cuda_bot cuda_worker cuda_db cuda_redis cuda_nginx; do
        if docker ps -a --format '{{.Names}}' | grep -q "^${container}$"; then
            echo "----------------------------------------"
            echo "Container: $container"
            echo "----------------------------------------"
            docker inspect $container 2>&1 | grep -A 5 "State\|Health\|Mounts\|Config" || echo "Could not inspect $container"
            echo ""
        fi
    done

    cd - > /dev/null

    # ===================================================================
    # 5. Container Logs
    # ===================================================================
    echo "========================================"
    echo "5. CONTAINER LOGS (last 500 lines each)"
    echo "========================================"
    echo ""

    for container in cuda_api cuda_bot cuda_worker cuda_db cuda_redis cuda_nginx; do
        if docker ps -a --format '{{.Names}}' | grep -q "^${container}$"; then
            echo "========================================"
            echo "Logs: $container"
            echo "========================================"
            docker logs --tail 500 $container 2>&1 || echo "Could not get logs for $container"
            echo ""
            echo ""
        fi
    done

    # ===================================================================
    # 6. Network Information
    # ===================================================================
    echo "========================================"
    echo "6. DOCKER NETWORKS"
    echo "========================================"
    echo ""

    echo "Docker networks:"
    docker network ls 2>&1
    echo ""

    echo "App network details:"
    docker network inspect infra_appnet 2>&1 || echo "Network not found"
    echo ""

    # ===================================================================
    # 7. Volume Information
    # ===================================================================
    echo "========================================"
    echo "7. DOCKER VOLUMES"
    echo "========================================"
    echo ""

    echo "Docker volumes:"
    docker volume ls 2>&1
    echo ""

    for vol in infra_pgdata infra_redisdata infra_uploads; do
        echo "Volume: $vol"
        docker volume inspect $vol 2>&1 || echo "Volume not found"
        echo ""
    done

    # ===================================================================
    # 8. Configuration Files
    # ===================================================================
    echo "========================================"
    echo "8. CONFIGURATION FILES"
    echo "========================================"
    echo ""

    if [ -f ".env" ]; then
        echo "--- .env (REDACTED) ---"
        # Show keys but hide values
        grep -v "^#" .env | grep "=" | sed 's/=.*/=***REDACTED***/' 2>&1
        echo ""
    else
        echo ".env file NOT found!"
        echo ""
    fi

    if [ -f "infra/docker-compose.prod.yml" ]; then
        echo "--- docker-compose.prod.yml ---"
        cat infra/docker-compose.prod.yml 2>&1
        echo ""
    fi

    if [ -f "infra/nginx.prod.conf" ]; then
        echo "--- nginx.prod.conf ---"
        cat infra/nginx.prod.conf 2>&1
        echo ""
    fi

    # ===================================================================
    # 9. Database Status
    # ===================================================================
    echo "========================================"
    echo "9. DATABASE STATUS"
    echo "========================================"
    echo ""

    cd infra 2>/dev/null || cd .

    if docker compose ps db &> /dev/null; then
        echo "PostgreSQL version:"
        docker compose exec -T db psql -U postgres -c "SELECT version();" 2>&1 || echo "Could not connect to DB"
        echo ""

        echo "Database list:"
        docker compose exec -T db psql -U postgres -c "\l" 2>&1 || echo "Could not list databases"
        echo ""

        echo "Tables in cudacrimea:"
        docker compose exec -T db psql -U postgres -d cudacrimea -c "\dt" 2>&1 || echo "Could not list tables"
        echo ""

        echo "Event count:"
        docker compose exec -T db psql -U postgres -d cudacrimea -c "SELECT COUNT(*) as total_events FROM events;" 2>&1 || echo "Could not count events"
        echo ""
    else
        echo "DB container not running"
        echo ""
    fi

    cd - > /dev/null

    # ===================================================================
    # 10. Redis Status
    # ===================================================================
    echo "========================================"
    echo "10. REDIS STATUS"
    echo "========================================"
    echo ""

    cd infra 2>/dev/null || cd .

    if docker compose ps redis &> /dev/null; then
        echo "Redis INFO:"
        docker compose exec -T redis redis-cli info 2>&1 | head -50 || echo "Could not get Redis info"
        echo ""

        echo "Redis DBSIZE:"
        docker compose exec -T redis redis-cli DBSIZE 2>&1 || echo "Could not get Redis key count"
        echo ""
    else
        echo "Redis container not running"
        echo ""
    fi

    cd - > /dev/null

    # ===================================================================
    # 11. Disk Usage
    # ===================================================================
    echo "========================================"
    echo "11. DISK USAGE"
    echo "========================================"
    echo ""

    echo "Filesystem usage:"
    df -h 2>&1
    echo ""

    echo "Docker system usage:"
    docker system df 2>&1
    echo ""

    echo "Project directory size:"
    du -sh . 2>&1
    echo ""

    # ===================================================================
    # 12. Process Information
    # ===================================================================
    echo "========================================"
    echo "12. PROCESS INFORMATION"
    echo "========================================"
    echo ""

    echo "Top processes by CPU:"
    ps aux --sort=-%cpu | head -10 2>&1 || top -bn1 | head -20 2>&1
    echo ""

    echo "Top processes by Memory:"
    ps aux --sort=-%mem | head -10 2>&1
    echo ""

    # ===================================================================
    # 13. Git Information
    # ===================================================================
    echo "========================================"
    echo "13. GIT INFORMATION"
    echo "========================================"
    echo ""

    if [ -d ".git" ]; then
        echo "Current branch:"
        git branch --show-current 2>&1
        echo ""

        echo "Last commit:"
        git log -1 --oneline 2>&1
        echo ""

        echo "Git status:"
        git status 2>&1
        echo ""
    else
        echo "Not a git repository"
        echo ""
    fi

    # ===================================================================
    # End of log collection
    # ===================================================================
    echo "========================================"
    echo "END OF LOG COLLECTION"
    echo "Generated: $(date)"
    echo "========================================"

} > "$OUTPUT_FILE" 2>&1

echo "✅ Logs collected successfully!"
echo "📁 Output file: $OUTPUT_FILE"
echo "📊 File size: $(du -h "$OUTPUT_FILE" | cut -f1)"
echo ""
echo "You can now send this file for debugging or analysis."
