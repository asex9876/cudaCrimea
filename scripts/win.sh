#!/usr/bin/env bash
set -euo pipefail

task="${1:-}"
compose="docker compose -f infra/docker-compose.yml"

case "$task" in
  up)
    $compose up -d --build
    ;;
  down)
    $compose down -v
    ;;
  logs)
    $compose logs -f --tail=200 api bot worker db redis nginx
    ;;
  ps)
    $compose ps
    ;;
  migrate)
    $compose exec api alembic -c app/db/alembic.ini upgrade head
    ;;
  seed)
    $compose exec api python -m app.scripts.seed
    ;;
  *)
    echo "Usage: bash scripts/win.sh [up|down|logs|ps|migrate|seed]" >&2
    exit 1
    ;;
esac

