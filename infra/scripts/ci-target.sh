#!/usr/bin/env sh
# `make ci-target` — гейт на целевой версии Python в контейнере (X-01).
#
# Зачем: целевая версия проекта — Python из .python-version (SPEC.md 2.2), а на машине
# разработки стоит другая. Без этой цели «зелёный локальный прогон» ничего не говорил
# о CI, и расхождение всплывало только после пуша. На 3.12 так уже всплывал RUF001,
# которого хостовый прогон не показывал.
#
# Что НЕ входит и почему:
#   * lint-hooks — pre-commit требует git-репозиторий и качает окружения хуков; в контейнере
#     .git это файл worktree, указывающий наружу, и хуки там не соберутся;
#   * integration-тесты — testcontainers поднимает контейнеры через docker-сокет, которого
#     внутри контейнера нет. Они проверяют SQL и сеть, а не версию интерпретатора (X-01).
#
# Цель ДОПОЛНЯЕТ `make ci`, а не заменяет её, и не заменяет GitHub Actions.
set -eu

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# Версия — из одного места на весь проект: .python-version читают и эта цель, и ci.yml.
PY_VERSION="$(tr -d ' \t\r\n' <"$ROOT/.python-version")"
PIP_CACHE_VOLUME="td-pipcache"

if ! docker info >/dev/null 2>&1; then
  echo "make ci-target: Docker не отвечает. Запусти Docker Desktop и повтори." >&2
  echo "Гейт на целевой версии Python без контейнера не прогнать; на хосте — make ci." >&2
  exit 1
fi

# Именованный volume под кэш pip: без него зависимости качаются заново каждый прогон.
# Ничего глобального не чистим и чужих volume не трогаем.
docker volume create "$PIP_CACHE_VOLUME" >/dev/null

echo "make ci-target: python:$PY_VERSION-slim"

# Кэши инструментов уводятся в /tmp контейнера: bind-mount — рабочее дерево разработчика,
# и мусор от прогона в нём не нужен.
exec docker run --rm \
  -v "$ROOT":/w \
  -w /w \
  -v "$PIP_CACHE_VOLUME":/root/.cache/pip \
  -e PIP_DISABLE_PIP_VERSION_CHECK=1 \
  -e RUFF_CACHE_DIR=/tmp/ruff \
  -e MYPY_CACHE_DIR=/tmp/mypy \
  -e PYTHONPYCACHEPREFIX=/tmp/pycache \
  "python:$PY_VERSION-slim" \
  sh -eu -c '
    # Каждая проверка — отдельной командой, без `&&`: в цепочке AND-OR оболочка
    # игнорирует `set -e` для всех звеньев, кроме последнего, и красный ruff уезжал бы
    # в зелёный прогон (проверено на живом падении, а не предположено).
    python -VV
    python -m pip install -q --root-user-action=ignore --upgrade pip
    python -m pip install -q --root-user-action=ignore -e "apps/api[dev]" -e "apps/collector-mt5[dev]"
    echo "--- ruff + mypy: apps/api"
    cd /w/apps/api
    ruff check .
    ruff format --check .
    mypy
    echo "--- ruff + mypy: apps/collector-mt5"
    cd /w/apps/collector-mt5
    ruff check .
    ruff format --check .
    mypy
    echo "--- pytest: apps/api (без integration — нет docker-сокета)"
    cd /w/apps/api
    pytest -m "not integration" -p no:cacheprovider
  '
