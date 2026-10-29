.PHONY: help install test lint check backup commands run docker-build docker-up docker-down

PYTHON ?= python3

help:
	@echo "Arush Manager Agent — CI/CD & Developer Commands"
	@echo "  make install       Install Python dependencies"
	@echo "  make lint          Run syntax & static code checks"
	@echo "  make test          Run unit & integration test suite (Phases 1-7)"
	@echo "  make check         Run startup diagnostics (--check-only)"
	@echo "  make backup        Run immediate hot backup of vault.sqlite & .env"
	@echo "  make commands      Register Telegram slash commands with Bot API"
	@echo "  make run           Start the Arush Manager Agent daemon"
	@echo "  make docker-build  Build production Docker image"
	@echo "  make docker-up     Start container stack via Docker Compose"
	@echo "  make docker-down   Stop container stack"

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

lint:
	$(PYTHON) -m py_compile config.py run.py bot/*.py core/*.py tools/*.py scripts/*.py tests/*.py
	@if command -v ruff >/dev/null 2>&1; then ruff check .; fi

test:
	$(PYTHON) -m unittest discover -s tests -p "test_*.py" -v

check:
	$(PYTHON) run.py --check-only

backup:
	$(PYTHON) run.py --backup-now

commands:
	$(PYTHON) run.py --set-commands

run:
	$(PYTHON) run.py

docker-build:
	docker build -t ghcr.io/arush221617/arush-tg:latest .

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down
