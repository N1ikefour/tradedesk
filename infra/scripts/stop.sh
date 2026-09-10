#!/usr/bin/env sh
# `make down` — SPEC.md 11.3. Гасит только сервисы этого проекта.
#
# Volume не трогаем: `down -v` стёр бы базу вместе со всеми сделками и рефлексиями.
# Удаление данных — отдельное осознанное действие, а не побочный эффект остановки.
set -eu

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

# Отсюда берутся td_cmd и печать через printf (X-64): в вывод попадает имя команды той
# платформы, на которой человек стоит, а `echo` съел бы обратные слэши `infra\scripts\…`.
TD_ROOT="$ROOT"
. "$ROOT/infra/scripts/common.sh"

if ! docker info >/dev/null 2>&1; then
  td_warn "Docker не отвечает — гасить нечего."
  exit 1
fi

# --profile local prod: без указания профилей compose не видит профильные сервисы и
# оставил бы web и caddy работать. Имя проекта из docker-compose.yml (`name: tradedesk`)
# ограничивает область: чужие контейнеры на машине не затрагиваются.
docker compose --profile local --profile prod down --remove-orphans

td_say ""
td_say "Остановлено. Данные в volume td_pgdata сохранены — следующий $(td_cmd up) поднимет их же."
