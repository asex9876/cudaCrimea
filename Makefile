SHELL := /bin/bash
COMPOSE := docker compose -f infra/docker-compose.yml
BACKUP_DIR := /opt/cudaCrimea/backups

.PHONY: help up down restart logs ps build migrate seed backup restore deploy health clean fmt lint test

##@ General

help: ## Показать эту справку
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Docker

up: ## Запустить все контейнеры
	$(COMPOSE) up -d

down: ## Остановить и удалить контейнеры
	$(COMPOSE) down

restart: ## Перезапустить все контейнеры
	$(COMPOSE) restart

stop: ## Остановить контейнеры без удаления
	$(COMPOSE) stop

start: ## Запустить остановленные контейнеры
	$(COMPOSE) start

build: ## Пересобрать контейнеры
	$(COMPOSE) build --no-cache

rebuild: down build up ## Полная пересборка (down + build + up)

ps: ## Показать статус контейнеров
	$(COMPOSE) ps

health: ## Быстрая проверка здоровья (запуск health-check.sh)
	@bash scripts/health-check.sh

health-docker: ## Проверить health status Docker контейнеров
	@echo "Checking health of services..."
	@$(COMPOSE) ps | grep -E "(healthy|unhealthy)" || echo "Health checks not configured"

diagnose: ## Полная диагностика системы (запуск diagnostics.sh)
	@bash scripts/diagnostics.sh

collect-logs: ## Собрать все логи в один файл
	@bash scripts/collect-logs.sh

##@ Logs

logs: ## Показать логи всех сервисов (follow mode)
	$(COMPOSE) logs -f --tail=200

logs-api: ## Логи API
	$(COMPOSE) logs -f --tail=200 api

logs-bot: ## Логи бота
	$(COMPOSE) logs -f --tail=200 bot

logs-worker: ## Логи worker
	$(COMPOSE) logs -f --tail=200 worker

logs-db: ## Логи PostgreSQL
	$(COMPOSE) logs -f --tail=200 db

logs-nginx: ## Логи nginx
	$(COMPOSE) logs -f --tail=200 nginx

##@ Database

migrate: ## Применить миграции
	$(COMPOSE) exec api alembic upgrade head

migrate-create: ## Создать новую миграцию (name=<name>)
	@if [ -z "$(name)" ]; then echo "Usage: make migrate-create name=<migration_name>"; exit 1; fi
	$(COMPOSE) exec api alembic revision --autogenerate -m "$(name)"

migrate-down: ## Откатить последнюю миграцию
	$(COMPOSE) exec api alembic downgrade -1

migrate-history: ## История миграций
	$(COMPOSE) exec api alembic history

seed: ## Заполнить БД тестовыми данными
	$(COMPOSE) exec api python -m app.scripts.seed

##@ Backup & Restore

backup: ## Создать backup базы данных
	@echo "Creating database backup..."
	@bash scripts/backup.sh

restore: ## Восстановить из backup (file=<path>)
	@if [ -z "$(file)" ]; then \
		echo "Usage: make restore file=<backup_file>"; \
		echo "Available backups:"; \
		ls -lh $(BACKUP_DIR)/backup_*.sql.gz 2>/dev/null || echo "No backups found"; \
		exit 1; \
	fi
	@bash scripts/restore.sh $(file)

list-backups: ## Список всех backup'ов
	@ls -lh $(BACKUP_DIR)/backup_*.sql.gz 2>/dev/null || echo "No backups found"

##@ Deployment

deploy: ## Развернуть/обновить на сервере
	@echo "Deploying cudaCrimea..."
	git pull origin main
	$(COMPOSE) down
	$(COMPOSE) build
	$(COMPOSE) up -d
	@echo "Waiting for services to start..."
	@sleep 10
	$(MAKE) migrate
	@echo "✓ Deployment completed!"

deploy-fresh: ## Развернуть с нуля (УДАЛИТ ВСЕ ДАННЫЕ!)
	@echo "⚠️  WARNING: This will delete all data!"
	@read -p "Are you sure? (yes/no): " -r; \
	if [[ ! $$REPLY =~ ^[Yy]es$$ ]]; then exit 1; fi
	$(COMPOSE) down -v
	$(COMPOSE) build
	$(COMPOSE) up -d
	@sleep 10
	$(MAKE) migrate
	@echo "✓ Fresh deployment completed!"

##@ Development

dev: ## Запустить в dev режиме с hot-reload
	ENV=dev $(COMPOSE) up

shell-api: ## Зайти в shell контейнера API
	$(COMPOSE) exec api /bin/bash

shell-db: ## Зайти в PostgreSQL shell
	$(COMPOSE) exec db psql -U postgres cudacrimea

shell-redis: ## Зайти в Redis CLI
	$(COMPOSE) exec redis redis-cli

fmt: ## Форматирование кода
	ruff format . && black . || true

lint: ## Проверка кода линтером
	ruff check .

test: ## Запустить тесты
	pytest -v

test-cov: ## Тесты с coverage
	pytest --cov=app --cov-report=html --cov-report=term

##@ Cleanup

clean: ## Очистить временные файлы
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true

clean-docker: ## Очистить Docker (образы, контейнеры, volumes)
	@echo "⚠️  This will remove all stopped containers, unused images, and volumes"
	@read -p "Continue? (yes/no): " -r; \
	if [[ ! $$REPLY =~ ^[Yy]es$$ ]]; then exit 1; fi
	docker system prune -af --volumes

##@ Admin

admin-shell: ## Открыть админ-панель в браузере
	@echo "Opening admin panel..."
	@echo "URL: http://localhost/admin/"
	@xdg-open http://localhost/admin/ 2>/dev/null || open http://localhost/admin/ 2>/dev/null || echo "Open http://localhost/admin/ in your browser"

admin-passwd: ## Создать/обновить пароль админа в htpasswd
	@read -p "Enter admin username: " username; \
	htpasswd -c infra/nginx.htpasswd $$username

parsers-run: ## Запустить все парсеры вручную
	$(COMPOSE) exec worker python -m app.ingestors.worker --once

parser-telegram: ## Запустить Telegram парсер
	$(COMPOSE) exec api python -m app.ingestors.telegram_channels

##@ Monitoring

stats: ## Статистика использования ресурсов
	docker stats --no-stream

disk-usage: ## Использование диска Docker
	docker system df

top: ## Процессы в контейнерах
	docker top cuda_api
	@echo "---"
	docker top cuda_bot
	@echo "---"
	docker top cuda_worker

