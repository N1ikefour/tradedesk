#!/usr/bin/env sh
# `make down` — SPEC.md 11.3. Гасит только сервисы этого проекта.
#
# Volume не трогаем: `down -v` стёр бы базу вместе со всеми сделками и рефлексиями.
# Удаление данных — отдельное осознанное действие, а не побочный эффект остановки.
set -eu

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if ! docker info >/dev/null 2>&1; then
  echo "Docker не отвечает — гасить нечего." >&2
  exit 1
fi

# --profile local prod: без указания профилей compose не видит профильные сервисы и
# оставил бы web и caddy работать. Имя проекта из docker-compose.yml (`name: tradedesk`)
# ограничивает область: чужие контейнеры на машине не затрагиваются.
docker compose --profile local --profile prod down --remove-orphans

echo ""
echo "Остановлено. Данные в volume td_pgdata сохранены — следующий make up поднимет их же."
