# ASTRA — common tasks.
#
# On Windows these run under Git Bash. `make` is not installed by default;
# every recipe is a single command line so it can also just be copied and run.

VENV_PY := ./.venv/Scripts/python.exe
ifeq ($(OS),)
VENV_PY := ./.venv/bin/python
endif

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

.PHONY: install
install: ## Create the venv and install every package in editable mode
	python -m venv .venv
	$(VENV_PY) -m pip install --upgrade pip
	$(VENV_PY) -m pip install -e packages/schema -e packages/rulepacks -e apps/vision -e apps/api
	$(VENV_PY) -m pip install pytest
	cd apps/web && npm install

.PHONY: test
test: ## Run every test suite
	$(VENV_PY) -m pytest

.PHONY: test-fast
test-fast: ## Run only the rule-engine tests (no OCR, under a second)
	$(VENV_PY) -m pytest packages/rulepacks/tests

.PHONY: demo
demo: ## Print the rule engine reasoning through seven real-world scenarios
	$(VENV_PY) scripts/demo_scenarios.py

.PHONY: seed
seed: ## Populate the database with synthetic inspections
	$(VENV_PY) scripts/seed_demo.py --count 70

.PHONY: eval
eval: ## Score the pipeline against ground truth and write docs/accuracy.md
	$(VENV_PY) ml/eval/report.py

.PHONY: api
api: ## Run the API on :8000
	$(VENV_PY) -m uvicorn app.main:app --reload --app-dir apps/api --port 8000

.PHONY: web
web: ## Run the dashboard and inspector on :3000
	cd apps/web && npm run dev

.PHONY: build
build: ## Production build of the frontend
	cd apps/web && npm run build

.PHONY: up
up: ## Bring the whole system up in containers, offline
	docker compose up --build

.PHONY: down
down: ## Stop the containers
	docker compose down

.PHONY: clean
clean: ## Remove the local database, uploads and caches
	rm -rf data/astra.db data/astra.db-wal data/astra.db-shm data/uploads data/evidence
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache apps/web/.next
