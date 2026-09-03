SHELL := /bin/bash
.DEFAULT_GOAL := help

ROOT          := $(CURDIR)
VENV          := $(ROOT)/.venv
VENV_BIN      := $(VENV)/bin
API_DIR       := $(ROOT)/apps/api
WEB_DIR       := $(ROOT)/apps/web
COLLECTOR_DIR := $(ROOT)/apps/collector-mt5

PYTHON ?= python3
NPM    ?= npm

# Локально инструменты берутся из .venv (см. make install), в CI — из PATH.
ifneq ($(wildcard $(VENV_BIN)/ruff),)
RUFF  := $(VENV_BIN)/ruff
MYPY  := $(VENV_BIN)/mypy
PYTEST := $(VENV_BIN)/pytest
PRECOMMIT := $(VENV_BIN)/pre-commit
else
RUFF  := ruff
MYPY  := mypy
PYTEST := pytest
PRECOMMIT := pre-commit
endif

.PHONY: help install hooks ci ci-api ci-web lint lint-api lint-collector lint-web lint-hooks \
        test test-api build-web format guard-python guard-precommit guard-web \
        init up down types

## ----------------------------------------------------------------------------
## Справка
## ----------------------------------------------------------------------------

help:
	@echo ""
	@echo "TradeDesk — команды разработки"
	@echo ""
	@echo "  Работают:"
	@echo "    make ci              ВЕСЬ гейт: то же самое и в том же составе, что гоняет GitHub Actions"
	@echo "                         (ci-api + ci-web). Перед PR прогоняется именно она"
	@echo "    make ci-api          джоб api: lint-api + lint-collector + lint-hooks + test-api"
	@echo "    make ci-web          джоб web: lint-web + build-web"
	@echo "    make install         установка dev-зависимостей (.venv для python, npm ci для web)"
	@echo "    make hooks           поставить git-хуки pre-commit (после make install)"
	@echo "    make lint            ruff + mypy (api, collector) + eslint + prettier --check + tsc (web)"
	@echo "    make lint-api        ruff check + ruff format --check + mypy для apps/api"
	@echo "    make lint-collector  ruff check + ruff format --check + mypy для apps/collector-mt5"
	@echo "    make lint-web        eslint + prettier --check + tsc --noEmit для apps/web"
	@echo "    make lint-hooks      pre-commit run --all-files (в т.ч. detect-private-key)"
	@echo "    make test            тесты: pytest (api). Тесты web (vitest) появятся в S0-07"
	@echo "    make test-api        pytest для apps/api"
	@echo "    make build-web       vite build для apps/web"
	@echo "    make format          ruff format + prettier --write"
	@echo "    make help            эта справка"
	@echo ""
	@echo "  Ещё не реализованы (падают с подсказкой, в какой задаче появятся):"
	@echo "    make init            .env из .env.example с генерацией секретов   → S0-06"
	@echo "    make up              docker compose --profile local up -d         → S0-06"
	@echo "    make down            остановка окружения                          → S0-06"
	@echo "    make migrate         alembic upgrade head"
	@echo "    make revision m=\"…\"  новая alembic-миграция (autogenerate)"
	@echo "    make downgrade       откат на шаг назад, make downgrade to=base"
	@echo "    make types           openapi → apps/web/src/api/schema.d.ts       → S0-07"
	@echo ""

## ----------------------------------------------------------------------------
## Установка окружения разработки
## ----------------------------------------------------------------------------

install:
	$(PYTHON) -m venv $(VENV)
	$(VENV_BIN)/python -m pip install --upgrade pip
	$(VENV_BIN)/python -m pip install -e "$(API_DIR)[dev]"
	$(VENV_BIN)/python -m pip install -e "$(COLLECTOR_DIR)[dev]"
	cd $(WEB_DIR) && $(NPM) ci
	@echo ""
	@echo "Готово. Git-хуки ставятся отдельно: make hooks"

hooks:
	$(VENV_BIN)/pre-commit install

guard-python:
	@command -v $(RUFF) >/dev/null 2>&1 || { \
	  echo "ruff/mypy/pytest не найдены. Запусти: make install"; exit 1; }

guard-precommit:
	@command -v $(PRECOMMIT) >/dev/null 2>&1 || { \
	  echo "pre-commit не найден. Запусти: make install"; exit 1; }

guard-web:
	@test -d $(WEB_DIR)/node_modules || { \
	  echo "apps/web/node_modules нет. Запусти: make install"; exit 1; }

## ----------------------------------------------------------------------------
## Гейт целиком. CI вызывает ci-api и ci-web, локально `make ci` = оба джоба.
## Расхождение локального прогона и CI — баг инфраструктуры, а не «особенность».
## ----------------------------------------------------------------------------

ci: ci-api ci-web

ci-api: lint-api lint-collector lint-hooks test-api

ci-web: lint-web build-web

## ----------------------------------------------------------------------------
## Отдельные проверки
## ----------------------------------------------------------------------------

lint: lint-api lint-collector lint-web

lint-api: guard-python
	cd $(API_DIR) && $(RUFF) check .
	cd $(API_DIR) && $(RUFF) format --check .
	cd $(API_DIR) && $(MYPY)

lint-collector: guard-python
	cd $(COLLECTOR_DIR) && $(RUFF) check .
	cd $(COLLECTOR_DIR) && $(RUFF) format --check .
	cd $(COLLECTOR_DIR) && $(MYPY)

lint-web: guard-web
	cd $(WEB_DIR) && $(NPM) run lint
	cd $(WEB_DIR) && $(NPM) run format:check
	cd $(WEB_DIR) && $(NPM) run typecheck

lint-hooks: guard-precommit
	$(PRECOMMIT) run --all-files

test: test-api
	@echo "тесты web (vitest) появятся в S0-07"

test-api: guard-python
	cd $(API_DIR) && $(PYTEST)

build-web: guard-web
	cd $(WEB_DIR) && $(NPM) run build

format: guard-python guard-web
	cd $(API_DIR) && $(RUFF) format .
	cd $(COLLECTOR_DIR) && $(RUFF) format .
	cd $(WEB_DIR) && $(NPM) run format

## ----------------------------------------------------------------------------
## Заглушки: команда задокументирована в CLAUDE.md 4, реализуется в своей задаче
## ----------------------------------------------------------------------------

init:
	@echo "make init ещё не реализована — задача S0-06 (docker compose local/prod, генерация секретов в .env)."
	@echo "Сейчас в репозитории только скелет монорепо (S0-01)."
	@exit 1

up:
	@echo "make up ещё не реализована — задача S0-06 (docker-compose.yml, профиль local)."
	@echo "Поднимать пока нечего: apps/api и apps/web — пустые каркасы."
	@exit 1

down:
	@echo "make down ещё не реализована — задача S0-06."
	@exit 1

migrate: guard-python
	cd $(API_DIR) && $(VENV_BIN)/alembic upgrade head

.PHONY: downgrade
downgrade: guard-python
	cd $(API_DIR) && $(VENV_BIN)/alembic downgrade $(or $(to),-1)

.PHONY: revision
revision: guard-python
	@test -n "$(m)" || { echo 'Нужно описание: make revision m="что меняем"'; exit 1; }
	cd $(API_DIR) && $(VENV_BIN)/alembic revision --autogenerate -m "$(m)"

types:
	@echo "make types ещё не реализована — задача S0-07 (openapi-typescript → apps/web/src/api/schema.d.ts)."
	@echo "Генерировать пока не из чего: эндпоинтов нет до S0-02."
	@exit 1
