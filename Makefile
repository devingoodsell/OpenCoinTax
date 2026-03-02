BACKEND_DIR := backend
FRONTEND_DIR := frontend
VENV := $(BACKEND_DIR)/venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest
ALEMBIC := $(VENV)/bin/alembic
UVICORN := $(VENV)/bin/uvicorn
LOG_DIR := logs

.PHONY: install run run-backend run-frontend stop test migrate migrate-generate \
        migrate-downgrade frontend-install frontend-dev frontend-build \
        frontend-test lint clean

# ── Backend ──────────────────────────────────────────────────────────

$(VENV)/bin/activate:
	rm -rf $(VENV)
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip

install: $(VENV)/bin/activate
	$(PIP) install -r $(BACKEND_DIR)/requirements.txt

run-backend: $(VENV)/bin/activate
	@mkdir -p $(LOG_DIR)
	@cd $(BACKEND_DIR) && $(abspath $(UVICORN)) app.main:app --reload --host 127.0.0.1 --port 8000 \
		> ../$(LOG_DIR)/backend.log 2>&1 & \
		echo "Backend PID: $$!"

run-frontend:
	@mkdir -p $(LOG_DIR)
	@cd $(FRONTEND_DIR) && npm run dev \
		> ../$(LOG_DIR)/frontend.log 2>&1 & \
		echo "Frontend PID: $$!"

run: run-backend run-frontend
	@echo "Logs: $(LOG_DIR)/backend.log, $(LOG_DIR)/frontend.log"
	@echo "Stop with: make stop"

stop:
	@-pkill -f 'uvicorn app.main:app' 2>/dev/null; true
	@-pkill -f 'vite' 2>/dev/null; true
	@echo "Stopped backend and frontend processes"

test: $(VENV)/bin/activate
	cd $(BACKEND_DIR) && $(PYTEST) -v --cov=app --cov-report=term-missing

migrate: $(VENV)/bin/activate
	cd $(BACKEND_DIR) && $(ALEMBIC) upgrade head

migrate-generate: $(VENV)/bin/activate
	cd $(BACKEND_DIR) && $(ALEMBIC) revision --autogenerate -m "$(msg)"

migrate-downgrade: $(VENV)/bin/activate
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

# ── Cleanup ──────────────────────────────────────────────────────────

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -type f -name '*.pyc' -delete 2>/dev/null; true
	rm -rf $(BACKEND_DIR)/data/*.db $(BACKEND_DIR)/data/*.db-wal $(BACKEND_DIR)/data/*.db-shm
	rm -rf $(LOG_DIR)
