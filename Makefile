.PHONY: help install dev worker clean build deploy logs stop reset-db format lint

help: ## Show this help message
	@echo 'Code Review Agent - Development Commands'
	@echo ''
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $1, $2}' $(MAKEFILE_LIST)

install: ## Install dependencies
	pip install --upgrade pip
	pip install -r requirements.txt

dev: ## Start development server
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

worker: ## Start Celery worker
	celery -A app.tasks.analysis_tasks worker --loglevel=info --concurrency=4

scheduler: ## Start Celery beat scheduler
	celery -A app.tasks.analysis_tasks beat --loglevel=info

format: ## Format code
	black app/
	isort app/

lint: ## Run linting
	black --check app/
	isort --check-only app/
	flake8 app/ --max-line-length=100 --ignore=E203,W503

clean: ## Clean up temporary files
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -name "*.log" -delete

build: ## Build Docker image
	docker build -t code-review-agent .

deploy: ## Deploy with Docker Compose
	docker-compose up -d

logs: ## Show logs
	docker-compose logs -f

stop: ## Stop all services
	docker-compose down

reset-db: ## Reset database
	alembic downgrade base
	alembic upgrade head

db-migrate: ## Create new database migration
	alembic revision --autogenerate -m "$(MSG)"

db-upgrade: ## Apply database migrations
	alembic upgrade head

shell: ## Start Python shell with app context
	python -c "from app.models import *; from app.services import *; print('App context loaded')"

monitor: ## Show system resources
	docker stats

backup-db: ## Backup database
	@echo "Creating database backup..."
	mkdir -p backups
	docker-compose exec db pg_dump -U postgres code_review_db > backups/backup_$(shell date +%Y%m%d_%H%M%S).sql

restore-db: ## Restore database (usage: make restore-db FILE=backup.sql)
	@if [ -z "$(FILE)" ]; then echo "Usage: make restore-db FILE=backup.sql"; exit 1; fi
	docker-compose exec -T db psql -U postgres code_review_db < $(FILE)

scale-workers: ## Scale worker instances (usage: make scale-workers N=4)
	@if [ -z "$(N)" ]; then echo "Usage: make scale-workers N=4"; exit 1; fi
	docker-compose up -d --scale worker=$(N)