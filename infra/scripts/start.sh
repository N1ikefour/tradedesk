#!/usr/bin/env sh
# `make up` — SPEC.md 11.3: поднять профиль local и сказать человеку, куда идти.
set -eu

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PROFILE="${PROFILE:-local}"

if [ ! -f "$ROOT/.env" ]; then
  echo "Нет $ROOT/.env — сначала запусти: make init" >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "Docker не отвечает. Запусти Docker Desktop и повтори." >&2
  exit 1
fi

if [ "$PROFILE" = "prod" ]; then
  # Без домена caddy не возьмёт сертификат и поднимется на пустом адресе сайта.
  DOMAIN_VALUE="$(grep -E '^DOMAIN=' "$ROOT/.env" | tail -1 | cut -d= -f2- | tr -d ' ' || true)"
  if [ -z "${DOMAIN_VALUE:-}" ]; then
    echo "Профиль prod требует DOMAIN в .env — под него caddy берёт автосертификат." >&2
    exit 1
  fi
fi

# --build: образ пересобирается при изменениях кода, иначе `make up` поднимал бы вчерашний
# API и разница «поправил и не помогло» стоила бы часа.
LOG="$(mktemp)"
trap 'rm -f "$LOG"' EXIT INT TERM
if ! docker compose --profile "$PROFILE" up -d --build 2>&1 | tee "$LOG"; then
  :
fi
if grep -qiE "port is already allocated|address already in use|bind for" "$LOG"; then
  echo "" >&2
  echo "Порт занят другой программой. TradeDesk слушает 5173 (web), 8000 (api)," >&2
  echo "5432 (postgres), 6379 (redis) — всё на 127.0.0.1." >&2
  echo "Освободи порт или задай другой в .env: WEB_PORT, API_PORT, POSTGRES_PORT, REDIS_PORT." >&2
  exit 1
fi
if ! docker compose --profile "$PROFILE" ps --status running --quiet | grep -q .; then
  echo "" >&2
  echo "Контейнеры не поднялись. Логи: docker compose --profile $PROFILE logs" >&2
  exit 1
fi

# Значения портов — из .env, если человек их менял.
WEB_PORT="$(grep -E '^WEB_PORT=' "$ROOT/.env" | tail -1 | cut -d= -f2 | tr -d ' ' || true)"
API_PORT="$(grep -E '^API_PORT=' "$ROOT/.env" | tail -1 | cut -d= -f2 | tr -d ' ' || true)"
WEB_PORT="${WEB_PORT:-5173}"
API_PORT="${API_PORT:-8000}"

echo ""
echo "TradeDesk поднят (профиль $PROFILE)."
echo ""
echo "  Приложение   http://localhost:$WEB_PORT"
echo "  API          http://localhost:$API_PORT/api/v1/health"
echo "  Документация http://localhost:$API_PORT/api/v1/docs"
echo ""
echo "Код для входа писем не шлёт: он лежит на странице"
echo "  http://localhost:$API_PORT/api/v1/dev/outbox"
echo "Искать его в логах не нужно — в логи код не попадает никогда."
echo ""
echo "Остановить: make down"
