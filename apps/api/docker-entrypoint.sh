#!/bin/sh
# Старт API: миграции, потом сервер (SPEC.md 11.1 — отдельного шага миграций нет).
set -eu

cd /srv/apps/api

echo "api: alembic upgrade head"
alembic upgrade head

# X-06. --forwarded-allow-ips ограничен конкретными адресами прокси из TRUSTED_PROXIES:
# со звёздочкой uvicorn берёт ПЕРВЫЙ элемент X-Forwarded-For, а его подставляет клиент —
# лимит по IP обходился бы одной строкой. Со списком адресов uvicorn идёт по цепочке
# справа и берёт первый недоверенный, как и app/core/client_ip.py.
# Пустой TRUSTED_PROXIES: заголовок не читается вовсе, адрес клиента — адрес соединения.
TRUSTED_PROXIES="${TRUSTED_PROXIES:-}"
if [ -n "$TRUSTED_PROXIES" ]; then
  set -- --proxy-headers --forwarded-allow-ips "$TRUSTED_PROXIES"
else
  echo "api: TRUSTED_PROXIES пуст — X-Forwarded-For игнорируется, лимит по IP пойдёт по адресу соединения" >&2
  set -- --no-proxy-headers
fi

echo "api: uvicorn на 0.0.0.0:8000"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 "$@"
