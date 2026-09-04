#!/usr/bin/env sh
# `make up` — SPEC.md 11.3: поднять профиль и сказать человеку, куда идти.
set -eu

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# Рабочий каталог — корень репозитория, а не тот, откуда позвали. start.bat запускается
# двойным кликом, и текущим каталогом там оказывается infra\scripts: без этой строки
# compose не находит docker-compose.yml, то есть штатный путь запуска не работает.
cd "$ROOT"

PROFILE="${PROFILE:-local}"
# Первый запуск на Windows с bind-mount тратит минуты на npm ci — ждём долго и терпеливо.
UP_TIMEOUT="${UP_TIMEOUT:-600}"

# Значение переменной из .env: последнее вхождение, без хвостового комментария и пробелов.
env_value() {
  grep -E "^$1=" "$ROOT/.env" 2>/dev/null |
    tail -1 |
    cut -d= -f2- |
    sed 's/[[:space:]]*#.*$//; s/^[[:space:]]*//; s/[[:space:]]*$//'
}

if [ ! -f "$ROOT/.env" ]; then
  echo "Нет $ROOT/.env — сначала запусти: make init" >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "Docker не отвечает. Запусти Docker Desktop и повтори." >&2
  exit 1
fi

if [ -z "$(env_value POSTGRES_PASSWORD)" ]; then
  echo "В .env пуст POSTGRES_PASSWORD — postgres откажется инициализировать базу." >&2
  echo "Его генерирует make init; если .env писался руками, задайте пароль и повторите." >&2
  exit 1
fi

if [ "$PROFILE" = "prod" ]; then
  # ⚠️ Гейт, без которого прод поднимается с открытым /api/v1/dev/outbox. Эта страница
  # отдаёт письма с кодами входа для ЛЮБОГО адреса почты, то есть даёт захватить любой
  # аккаунт. Роутер выключается только по APP_ENV=prod (app/main.py), и штатный .env
  # приезжает со значением local — то есть по умолчанию прод открыт настежь.
  APP_ENV_VALUE="$(env_value APP_ENV)"
  if [ "$APP_ENV_VALUE" != "prod" ]; then
    echo "Профиль prod, а в .env APP_ENV='$APP_ENV_VALUE'. Запуск отменён." >&2
    echo "" >&2
    echo "При APP_ENV != prod приложение публикует /api/v1/dev/outbox — страницу с кодами" >&2
    echo "входа для любого адреса почты. В интернете это захват любого аккаунта." >&2
    echo "Поставь APP_ENV=prod в .env и повтори." >&2
    exit 1
  fi
  # Плейсхолдер тоже непустой, поэтому проверки на пустоту мало: под этим именем caddy
  # пойдёт за сертификатом Let's Encrypt на чужой домен.
  DOMAIN_VALUE="$(env_value DOMAIN)"
  case "$DOMAIN_VALUE" in
    "" | localhost | *.local | *.invalid | \
    example.com | *.example.com | example.org | *.example.org | example.net | *.example.net)
      echo "Профиль prod требует настоящий DOMAIN в .env, сейчас там '$DOMAIN_VALUE'." >&2
      echo "Под это имя caddy запрашивает сертификат Let's Encrypt: с плейсхолдером" >&2
      echo "это запрос на чужой домен и гарантированный отказ." >&2
      exit 1
      ;;
  esac
fi

# --build: образ пересобирается при изменениях кода, иначе `make up` поднимал бы вчерашний
# API и разница «поправил и не помогло» стоила бы часа.
LOG="$(mktemp)"
STATUS_FILE="$(mktemp)"
trap 'rm -f "$LOG" "$STATUS_FILE"' EXIT INT TERM

# tee оставляет сборку видимой в реальном времени, но код возврата конвейера — код tee,
# и он всегда 0. Настоящий статус compose уносим отдельным файлом: иначе `make up`
# рапортует «поднят» поверх упавшей сборки.
{ docker compose --profile "$PROFILE" up -d --build 2>&1; echo "$?" >"$STATUS_FILE"; } | tee "$LOG"
UP_STATUS="$(cat "$STATUS_FILE")"

if grep -qiE "port is already allocated|address already in use|bind for" "$LOG"; then
  echo "" >&2
  echo "Порт занят другой программой. TradeDesk слушает 5173 (web), 8000 (api)," >&2
  echo "5432 (postgres), 6379 (redis) — всё на 127.0.0.1." >&2
  echo "Освободи порт или задай другой в .env: WEB_PORT, API_PORT, POSTGRES_PORT, REDIS_PORT." >&2
  exit 1
fi

if [ "$UP_STATUS" != "0" ]; then
  echo "" >&2
  echo "docker compose up завершился с кодом $UP_STATUS — окружение не поднято." >&2
  exit 1
fi

SERVICES="$(docker compose --profile "$PROFILE" config --services)"

# "<состояние> <здоровье>" одного сервиса; healthcheck есть не у всех — тогда "none".
service_state() {
  cid="$(docker compose --profile "$PROFILE" ps -a -q "$1" 2>/dev/null || true)"
  if [ -z "$cid" ]; then
    echo "missing none"
    return
  fi
  docker inspect -f \
    '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
    "$cid" 2>/dev/null || echo "missing none"
}

report_broken() {
  echo "" >&2
  echo "Не поднялись сервисы:$1" >&2
  echo "" >&2
  for service in $1; do
    echo "--- последние строки лога $service ---" >&2
    docker compose --profile "$PROFILE" logs --tail 25 "$service" >&2 2>/dev/null || true
  done
  echo "" >&2
  echo "Полные логи: docker compose --profile $PROFILE logs" >&2
}

# Проверяется КАЖДЫЙ сервис профиля, а не «хоть один живой»: postgres и redis поднимаются
# всегда, и по ним нельзя судить об api. Падающий api виден как restarting, а не как
# отсутствие контейнера, поэтому мало и `ps --status running`.
wait_for_services() {
  deadline=$(( $(date +%s) + UP_TIMEOUT ))
  announced=0
  while :; do
    pending=""
    broken=""
    for service in $SERVICES; do
      info="$(service_state "$service")"
      state="${info%% *}"
      health="${info##* }"
      case "$state" in
        running)
          case "$health" in
            healthy | none) ;;
            starting) pending="$pending $service" ;;
            *) broken="$broken $service" ;;
          esac
          ;;
        created) pending="$pending $service" ;;
        restarting | exited | dead | paused | removing | missing) broken="$broken $service" ;;
        *) pending="$pending $service" ;;
      esac
    done

    if [ -n "$broken" ]; then
      report_broken "$broken"
      return 1
    fi
    if [ -z "$pending" ]; then
      return 0
    fi
    if [ "$(date +%s)" -ge "$deadline" ]; then
      echo "" >&2
      echo "Не дождались за ${UP_TIMEOUT} с:$pending" >&2
      echo "Первый запуск ставит зависимости web и может быть долгим — увеличь UP_TIMEOUT." >&2
      report_broken "$pending"
      return 1
    fi
    if [ "$announced" = "0" ]; then
      echo ""
      echo "Ждём готовности:$pending (до ${UP_TIMEOUT} с)"
      announced=1
    fi
    sleep 2
  done
}

wait_for_services || exit 1
# Контрольная пауза: сервис без healthcheck успевает упасть уже после первой проверки,
# и без второго взгляда `make up` снова отрапортовал бы успех поверх падения.
sleep 3
wait_for_services || exit 1

WEB_PORT="$(env_value WEB_PORT)"
API_PORT="$(env_value API_PORT)"
WEB_PORT="${WEB_PORT:-5173}"
API_PORT="${API_PORT:-8000}"

echo ""
echo "TradeDesk поднят (профиль $PROFILE)."
echo ""
if [ "$PROFILE" = "local" ]; then
  echo "  Приложение   http://localhost:$WEB_PORT"
  echo "  API          http://localhost:$API_PORT/api/v1/health"
  echo "  Документация http://localhost:$API_PORT/api/v1/docs"
  echo ""
  echo "Код для входа писем не шлёт: он лежит на странице"
  echo "  http://localhost:$API_PORT/api/v1/dev/outbox"
  echo "Искать его в логах не нужно — в логи код не попадает никогда."
else
  echo "  Приложение   https://$(env_value DOMAIN)"
fi
echo ""
echo "Остановить: make down"
