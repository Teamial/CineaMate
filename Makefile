.PHONY: help dev down logs ps dbshell localstack test lint fmt infra-plan infra-apply

COMPOSE ?= docker compose
COMPOSE_FILE ?= deployment/docker-compose.yml

help:
	@echo "Targets:"
	@echo "  make dev            Start dev stack (db + localstack + backend)"
	@echo "  make down           Stop dev stack"
	@echo "  make logs           Tail logs"
	@echo "  make ps             Show running containers"
	@echo "  make dbshell        Open psql shell in db container"
	@echo "  make localstack     Show localstack health"
	@echo "  make test           Run backend tests in container"
	@echo "  make lint           Run basic backend lint (python -m compileall + pytest -q)"
	@echo "  make fmt            No-op placeholder (add ruff/black later)"
	@echo "  make infra-plan ENV=staging|production   Terraform plan (LocalStack)"
	@echo "  make infra-apply ENV=staging|production  Terraform apply (LocalStack)"

dev:
	$(COMPOSE) -f $(COMPOSE_FILE) up -d --build

down:
	$(COMPOSE) -f $(COMPOSE_FILE) down -v

logs:
	$(COMPOSE) -f $(COMPOSE_FILE) logs -f --tail=200

ps:
	$(COMPOSE) -f $(COMPOSE_FILE) ps

dbshell:
	$(COMPOSE) -f $(COMPOSE_FILE) exec db psql -U postgres -d movies_db

localstack:
	$(COMPOSE) -f $(COMPOSE_FILE) exec localstack bash -lc "curl -sSf http://localhost:4566/_localstack/health | head -c 200 && echo"

test:
	$(COMPOSE) -f $(COMPOSE_FILE) run --rm backend pytest -q backend/tests

lint:
	$(COMPOSE) -f $(COMPOSE_FILE) run --rm backend python -m compileall -q backend && \
	$(COMPOSE) -f $(COMPOSE_FILE) run --rm backend pytest -q backend/tests

fmt:
	@echo "Format step not yet configured (ruff/black)."

infra-plan:
	cd infra/environments/$(ENV) && terraform init -upgrade && terraform fmt -recursive && terraform validate && terraform plan

infra-apply:
	cd infra/environments/$(ENV) && terraform init -upgrade && terraform apply -auto-approve

