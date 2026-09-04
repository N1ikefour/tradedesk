# Образ API. Контекст сборки — корень репозитория: alembic.ini и alembic/ лежат рядом с app/.
# Версия питона одна на весь проект и живёт в .python-version (см. Makefile, ci.yml).
FROM python:3.12-slim

# PYTHONDONTWRITEBYTECODE: .pyc в bind-mount репозитория никому не нужны.
# PYTHONUNBUFFERED: без него логи приложения не видны в `docker compose logs` до сброса буфера.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

# Зависимости ставятся отдельным слоем от кода: правка app/ не переустанавливает fastapi.
# Пустой пакет-заглушка нужен только чтобы pip разобрал pyproject и поставил зависимости.
COPY apps/api/pyproject.toml /srv/apps/api/pyproject.toml
RUN mkdir -p /srv/apps/api/app \
 && touch /srv/apps/api/app/__init__.py \
 && python -m pip install --upgrade pip \
 && python -m pip install /srv/apps/api

COPY apps/api /srv/apps/api

# --no-deps: зависимости уже стоят слоем выше, второй проход только подменяет сам пакет
# на editable — иначе `importlib.metadata.version` не увидит tradedesk-api и версия
# в /api/v1/version станет 0.0.0+unknown.
RUN python -m pip install --no-deps -e /srv/apps/api

# Приложение работает не от root: контейнер с published port не должен давать root в томах.
RUN useradd --create-home --uid 10001 app && chown -R app:app /srv
USER app

WORKDIR /srv/apps/api
EXPOSE 8000
ENTRYPOINT ["/srv/apps/api/docker-entrypoint.sh"]
