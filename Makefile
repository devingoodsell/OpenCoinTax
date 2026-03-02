BACKEND_DIR := backend
FRONTEND_DIR := frontend
VENV := $(BACKEND_DIR)/venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest
ALEMBIC := $(VENV)/bin/alembic
UVICORN := $(VENV)/bin/uvicorn

.PHONY: venv install run test migrate migrate-generate migrate-downgrade \
        frontend-install frontend-dev frontend-build frontend-test \
        dev lint clean

# ── Backend ──────────────────────────────────────────────────────────

venv:
	python3 -m venv $(VENV)

install: venv
	$(PIP) install -r $(BACKEND_DIR)/requirements.txt

run:
	cd $(BACKEND_DIR) && $(UVICORN) app.main:app --reload --host 127.0.0.1 --port 8000

test:
	cd $(BACKEND_DIR) && $(PYTEST) -v --cov=app --cov-report=term-missing

migrate:
	cd $(BACKEND_DIR) && $(ALEMBIC) upgrade head

migrate-generate:
	cd $(BACKEND_DIR) && $(ALEMBIC) revision --autogenerate -m "$(msg)"

migrate-downgrade:
	cd $(BACKEND_DIR) && $(ALEMBIC) downgrade -1

# ── Frontend ─────────────────────────────────────────────────────────

frontend-install:
	cd $(FRONTEND_DIR) && npm install

frontend-dev:
	cd $(FRONTEND_DIR) && npm run dev

frontend-build:
	cd $(FRONTEND_DIR) && npm run build

frontend-test:
	cd $(FRONTEND_DIR) && npm run test:coverage

# ── Combined ─────────────────────────────────────────────────────────

dev:
	@echo "Start backend and frontend in separate terminals:"
	@echo "  Terminal 1: make run"
	@echo "  Terminal 2: make frontend-dev"

# ── Cleanup ──────────────────────────────────────────────────────────

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -type f -name '*.pyc' -delete 2>/dev/null; true
	rm -rf $(BACKEND_DIR)/data/*.db $(BACKEND_DIR)/data/*.db-wal $(BACKEND_DIR)/data/*.db-shm
