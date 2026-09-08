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

# Целевая версия Python — одна на весь проект: этот файл, .github/workflows/ci.yml
# (python-version-file) и apps/api/Dockerfile читают одно и то же .python-version.
PY_VERSION := $(shell tr -d ' \t\r\n' < $(ROOT)/.python-version)

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

SCRIPTS := $(ROOT)/infra/scripts

.PHONY: help install hooks ci ci-api ci-web ci-target lint lint-api lint-collector lint-web \
        lint-hooks test test-api test-web test-release test-scripts build-web smoke format \
        guard-python \
        guard-precommit guard-web init up down backup restore update migrate downgrade \
        revision types release

## ----------------------------------------------------------------------------
## Справка
## ----------------------------------------------------------------------------

help:
	@echo ""
	@echo "TradeDesk — команды разработки"
	@echo ""
	@echo "  Работают:"
	@echo "    make init            .env из .env.example с генерацией секретов."
	@echo "                         Существующий .env НЕ перезаписывает: в нём MASTER_KEY"
	@echo "    make up              docker compose --profile local up -d --build, печатает URL"
	@echo "    make down            остановка окружения, данные в volume остаются"
	@echo "    make backup          дамп базы в backups/td-<дата>.sql.gz, дамп проверяется,"
	@echo "                         остаются последние 14 по времени создания"
	@echo "    make restore file=backups/td-….sql.gz"
	@echo "                         восстановить базу из бэкапа. Показывает, что перезапишет,"
	@echo "                         и снимает страховочный бэкап перед заливкой"
	@echo "    make update          обновиться до последнего релиза: сверка MASTER_KEY,"
	@echo "                         бэкап, распаковка архива поверх установки, build, up."
	@echo "                         make update ARGS=--check — только проверить"
	@echo "    make ci              ВЕСЬ гейт: то же самое и в том же составе, что гоняет GitHub Actions"
	@echo "                         (ci-api + ci-web). Перед PR прогоняется именно она"
	@echo "    make ci-api          джоб api: lint-api + lint-collector + lint-hooks +"
	@echo "                         test-api + test-release + test-scripts"
	@echo "    make ci-web          джоб web: lint-web + test-web + build-web"
	@echo "    make ci-target       ruff + mypy + unit-тесты в контейнере python:$(PY_VERSION)-slim —"
	@echo "                         на целевой версии, которой нет на машине. ДОПОЛНЯЕТ make ci,"
	@echo "                         не заменяет её: без pre-commit и integration-тестов"
	@echo "    make install         установка dev-зависимостей (.venv для python, npm ci для web)"
	@echo "    make hooks           поставить git-хуки pre-commit (после make install)"
	@echo "    make lint            ruff + mypy (api, collector) + eslint + prettier --check + tsc (web)"
	@echo "    make lint-api        ruff check + ruff format --check + mypy для apps/api"
	@echo "    make lint-collector  ruff check + ruff format --check + mypy для apps/collector-mt5"
	@echo "    make lint-web        eslint + prettier --check + tsc --noEmit для apps/web"
	@echo "    make lint-hooks      pre-commit run --all-files (в т.ч. detect-private-key)"
	@echo "    make test            тесты: pytest (api) + vitest (web)"
	@echo "    make test-api        pytest для apps/api"
	@echo "    make test-web        vitest run для apps/web"
	@echo "    make test-release    тесты сборщика релизного архива (состав, симлинки,"
	@echo "                         секреты, форма тега). Входит в make ci-api"
	@echo "    make test-scripts    проверки backup/restore/update без докера: битый дамп,"
	@echo "                         ротация, предпросмотр restore, сверка MASTER_KEY,"
	@echo "                         разбор версии. Входит в make ci-api"
	@echo "    make build-web       vite build для apps/web"
	@echo "    make smoke           playwright-смоук входа против поднятого make up."
	@echo "                         В make ci НЕ входит: браузеры ставятся отдельно"
	@echo "                         (npx playwright install chromium), см. цель smoke"
	@echo "    make types           openapi запущенного api → apps/web/src/api/schema.d.ts."
	@echo "                         Требует make up (профиль local)"
	@echo "    make format          ruff format + prettier --write"
	@echo "    make release VERSION=vX.Y.Z"
	@echo "                         релизный zip в dist/ (ADR-0005). Тег проставляется"
	@echo "                         в версию пакета: /api/v1/version отдаст ровно его."
	@echo "                         Ту же цель по тегу вызывает .github/workflows/release.yml"
	@echo "    make migrate         alembic upgrade head (в .venv; в контейнере это делает старт api)"
	@echo "    make revision m=\"…\"  новая alembic-миграция (autogenerate)"
	@echo "    make downgrade       откат на шаг назад, make downgrade to=base"
	@echo "    make help            эта справка"
	@echo ""
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

# test-release живёт в этом джобе, а не в web: ему нужны python3, git и zip — ровно то,
# что уже стоит на api-раннере. Гейт на артефакт больше нигде не появится: релизный
# workflow запускается по тегу, то есть после того, как ломать уже поздно.
ci-api: lint-api lint-collector lint-hooks test-api test-release test-scripts

ci-web: lint-web test-web build-web

# Гейт на целевой версии Python в контейнере (X-01). Дополняет `make ci`, не заменяет её:
# вторая равноправная цель рано или поздно разошлась бы с первой. Авторитетный прогон —
# по-прежнему GitHub Actions. Что именно и почему не входит — в самом скрипте.
ci-target:
	@$(SCRIPTS)/ci-target.sh

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

test: test-api test-web

test-api: guard-python
	cd $(API_DIR) && $(PYTEST)

test-web: guard-web
	cd $(WEB_DIR) && $(NPM) run test

build-web: guard-web
	cd $(WEB_DIR) && $(NPM) run build

# Тесты сборщика релизного архива. Единственная проверка того, что уезжает пользователю:
# ни один другой прогон в проекте состав архива не смотрит.
test-release:
	@$(SCRIPTS)/test-make-release.sh

# Всё, на чём держатся backup, restore и update, вынесено в common.sh чистыми функциями —
# и проверяется здесь без докера: разбор дампа, ротация (она удаляет файлы), предпросмотр
# restore, сверка MASTER_KEY, разбор версии. Что осталось за докером — сказано в скрипте.
test-scripts:
	@$(SCRIPTS)/test-scripts.sh

# Смоук входа (SPEC.md 13) против поднятого `make up`. Отдельная цель, а не часть `make ci`:
# браузеры Playwright ставятся сотнями мегабайт и нужны одному тесту, а из набора SPEC.md 13
# сейчас достижим только вход — остальных экранов ещё нет. Зовётся осознанно.
smoke: guard-web
	@test -d "$${PLAYWRIGHT_BROWSERS_PATH:-$$HOME/Library/Caches/ms-playwright}" || \
	  test -d "$$HOME/.cache/ms-playwright" || { \
	    echo "Браузеров Playwright нет. Поставь: cd apps/web && npx playwright install chromium"; \
	    exit 1; }
	cd $(WEB_DIR) && $(NPM) run smoke

format: guard-python guard-web
	cd $(API_DIR) && $(RUFF) format .
	cd $(COLLECTOR_DIR) && $(RUFF) format .
	cd $(WEB_DIR) && $(NPM) run format

## ----------------------------------------------------------------------------
## Локальное окружение (SPEC.md 11). Логика — в infra/scripts: те же скрипты вызывают
## start.bat/stop.bat на Windows, и чинить её приходится в одном месте, а не в двух.
## ----------------------------------------------------------------------------

init:
	@$(SCRIPTS)/init-env.sh

up:
	@$(SCRIPTS)/start.sh

down:
	@$(SCRIPTS)/stop.sh

# Резервная копия и восстановление (SPEC.md 11.3). Единственные команды, которые человек
# запускает на СВОИХ данных: всё остальное в проекте перезапускается с нуля, а потерянный
# журнал не восстанавливает никто. Логика — в скриптах, здесь только вход.
backup:
	@$(SCRIPTS)/backup.sh

restore:
	@test -n "$(file)" || { \
	  echo 'Нужен файл: make restore file=backups/td-20260907-120000.sql.gz'; \
	  ls -t backups/td-*.sql.gz 2>/dev/null | sed 's|^|    |'; exit 1; }
	@$(SCRIPTS)/restore.sh "$(file)"

update:
	@$(SCRIPTS)/update.sh $(ARGS)

migrate: guard-python
	cd $(API_DIR) && $(VENV_BIN)/alembic upgrade head

.PHONY: downgrade
downgrade: guard-python
	cd $(API_DIR) && $(VENV_BIN)/alembic downgrade $(or $(to),-1)

.PHONY: revision
revision: guard-python
	@test -n "$(m)" || { echo 'Нужно описание: make revision m="что меняем"'; exit 1; }
	cd $(API_DIR) && $(VENV_BIN)/alembic revision --autogenerate -m "$(m)"

# Типы фронта из OpenAPI запущенного api (S0-07). Схема берётся у живого приложения,
# а не из файла в репозитории: файл пришлось бы обновлять руками, и он расходился бы
# с API молча. Профиль обязан быть local — только там объявлен /api/v1/dev/outbox.
types: guard-web
	cd $(WEB_DIR) && $(NPM) run gen:types

## ----------------------------------------------------------------------------
## Релиз (ADR-0005). Пользователь получает zip со страницы релизов, не клон репозитория.
## CI зовёт эту же цель по тегу — расхождение сборки «у человека» и «в CI» здесь стоило бы
## дороже обычного: артефакт и есть продукт, другого способа его получить у человека нет.
## ----------------------------------------------------------------------------

# VERSION приходит рецепту окружением, а не подстановкой $(VERSION) в тело: подстановку
# make делает ДО того, как строку увидит sh, поэтому тег вида `v1.0.0"; rm -rf /; echo "`
# выполнялся бы как код. Значение тега контролирует любой, кто может запушить тег, а джоб
# release.yml ходит с contents: write — то есть это был бы путь от тега до чужой команды
# в раннере. Проверка формы в самом скрипте от этого не спасает: она получает уже
# расщеплённый шеллом аргумент. Через окружение sh значение не интерпретирует.
export VERSION
export OUT

release:
	@test -n "$$VERSION" || { echo 'Нужна версия: make release VERSION=v0.1.0'; exit 1; }
	@$(SCRIPTS)/make-release.sh "$$VERSION" "$${OUT:-$(ROOT)/dist}"
