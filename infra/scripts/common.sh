#!/usr/bin/env sh
# Общая часть backup/restore/update (SPEC.md 11.3). Сам по себе не запускается — только
# `. common.sh` из скрипта, который уже определил TD_ROOT.
#
# Почему отдельный файл: три скрипта делают одно и то же с .env, docker и postgres, и
# расхождение этих кусков стоило бы данных. `.bat`-обёртки логики не содержат вовсе
# (см. start.bat) — значит, версия на Windows и на macOS ровно одна, и разойтись им негде.
#
# ⚠️ Значения секретов из .env здесь не читаются и не печатаются никогда. MASTER_KEY
# проверяется только на присутствие (`td_env_present`), а его отпечаток считает контейнер
# api из своего env_file — в переменную shell ключ не попадает ни на секунду.

# Профиль compose. `local` — установка у тестировщика, `prod` — вариант с caddy.
PROFILE="${PROFILE:-local}"

# Таблицы, чьи счётчики человек видит перед восстановлением. Это тот самый слой, который
# нигде больше не хранится: брокер помнит сделки, рефлексии не помнит никто.
TD_COUNTED_TABLES="users trading_accounts deals positions journal_entries reflections tags attachments"

td_die() {
  echo "" >&2
  echo "$1" >&2
  exit "${2:-1}"
}

td_say() {
  echo "$1"
}

# Значение переменной из .env: последнее вхождение, без хвостового комментария и пробелов.
# Та же логика, что в start.sh. Секреты этой функцией не читаются.
td_env_value() {
  grep -E "^$1=" "$TD_ROOT/.env" 2>/dev/null |
    tail -1 |
    cut -d= -f2- |
    sed 's/[[:space:]]*#.*$//; s/^[[:space:]]*//; s/[[:space:]]*$//'
}

# Присутствие переменной с непустым значением. Значение наружу не выходит — ни в
# переменную, ни в вывод: это единственный способ проверить MASTER_KEY, не касаясь его.
td_env_present() {
  grep -qE "^$1=[[:space:]]*[^[:space:]#]" "$TD_ROOT/.env" 2>/dev/null
}

td_require_installation() {
  for required in docker-compose.yml .env.example infra/scripts/start.sh; do
    [ -e "$TD_ROOT/$required" ] ||
      td_die "$TD_ROOT не похож на установку TradeDesk — нет $required.
Запускать скрипт нужно из папки, в которую распакован архив."
  done
}

# ⚠️ ADR-0005. Без .env нет MASTER_KEY, а без него пароли брокерских счетов в томе
# нечитаемы навсегда. Молча создать новый .env здесь — худшее, что может сделать скрипт.
td_require_env() {
  if [ ! -f "$TD_ROOT/.env" ]; then
    td_die "Нет $TD_ROOT/.env — обновлять и резервировать нечего.

Это не «сейчас создадим»: в .env лежит MASTER_KEY, которым зашифрованы пароли
брокерских счетов в базе. Новый ключ откроет приложение, но не откроет пароли —
и коллектор перестанет заходить в терминал, а выяснится это через сутки.

Если вы распаковали новую версию в отдельную папку — вернитесь в папку старой
установки и запустите скрипт оттуда: и обновление, и резервная копия работают
внутри установки, а не рядом с ней.
Если .env потерян — восстановите его из своей копии. Другого пути нет."
  fi
  td_env_present MASTER_KEY ||
    td_die "В $TD_ROOT/.env пуст MASTER_KEY — им зашифрованы пароли счетов.
Пустой ключ означает либо испорченный .env, либо чужой файл. Скрипт остановлен."
}

td_require_docker() {
  docker info >/dev/null 2>&1 ||
    td_die "Docker не отвечает. Запустите Docker Desktop и повторите."
}

td_compose() {
  docker compose --profile "$PROFILE" "$@"
}

td_service_status() {
  cid="$(td_compose ps -a -q "$1" 2>/dev/null || true)"
  if [ -z "$cid" ]; then
    echo "missing none"
    return
  fi
  docker inspect -f \
    '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
    "$cid" 2>/dev/null || echo "missing none"
}

# Postgres поднят и принимает соединения. Нужен и бэкапу, и сверке ключа: без базы
# ни то ни другое сделать нельзя, а «база лежит» — не повод молча пропустить проверку.
td_ensure_postgres() {
  info="$(td_service_status postgres)"
  case "${info%% *}" in
    running) ;;
    *)
      td_say "Поднимаю postgres…"
      td_compose up -d postgres >/dev/null 2>&1 ||
        td_die "Не удалось поднять postgres. Логи: docker compose logs postgres"
      ;;
  esac

  deadline=$(($(date +%s) + 120))
  while :; do
    info="$(td_service_status postgres)"
    state="${info%% *}"
    health="${info##* }"
    [ "$state" = "running" ] && [ "$health" = "healthy" ] && break
    case "$state" in
      exited | dead | missing)
        td_compose logs --tail 25 postgres >&2 2>/dev/null || true
        td_die "postgres не запустился."
        ;;
    esac
    [ "$(date +%s)" -lt "$deadline" ] ||
      td_die "postgres не стал healthy за 120 с. Логи: docker compose logs postgres"
    sleep 2
  done

  # Имя пользователя и базы берём у самого контейнера, а не константой в скрипте:
  # разойтись с docker-compose.yml здесь означало бы «pg_dump: database does not exist»
  # на середине обновления.
  creds="$(td_compose exec -T postgres sh -c 'printf "%s %s" "$POSTGRES_USER" "$POSTGRES_DB"')" ||
    td_die "Не удалось прочитать POSTGRES_USER/POSTGRES_DB у контейнера postgres."
  TD_PG_USER="${creds%% *}"
  TD_PG_DB="${creds##* }"
  [ -n "$TD_PG_USER" ] && [ -n "$TD_PG_DB" ] ||
    td_die "У контейнера postgres пусты POSTGRES_USER/POSTGRES_DB."
}

# Одна строка ответа, без заголовков и рамок.
td_psql() {
  td_compose exec -T postgres \
    psql -X -q -A -t -v ON_ERROR_STOP=1 -U "$TD_PG_USER" -d "$TD_PG_DB" -c "$1"
}

td_table_exists() {
  [ "$(td_psql "select to_regclass('public.$1') is not null" | tr -d '\r ')" = "t" ]
}

# «имя<TAB>строк» по таблицам, которые реально есть. Отсутствующая таблица пропускается:
# на свежем томе их нет вовсе, и это не повод падать.
td_table_counts() {
  for table in $TD_COUNTED_TABLES; do
    if td_table_exists "$table"; then
      printf '%s\t%s\n' "$table" "$(td_psql "select count(*) from public.$table" | tr -d '\r ')"
    fi
  done
}

td_print_counts() {
  while IFS="$(printf '\t')" read -r table count; do
    printf '    %-20s %s\n' "$table" "$count"
  done
}

# Один проход по распакованному дампу: какие таблицы в нём созданы, сколько строк в каждом
# блоке COPY и дочитался ли дамп до конца. Отсюда живут обе проверки — и «бэкап целый»
# в backup, и «вот что вы получите» в restore.
#
# Разбор идёт конечным автоматом, а не грепом: внутри блока COPY лежит текст пользователя,
# и заметка со строкой «COPY public.positions … FROM stdin;» иначе увела бы счётчик.
# В блоке COPY значима ровно одна строка — `\.`; настоящие данные Postgres экранирует.
#
# Печатает строки: `TABLE <имя> <строк>`, `CREATED <имя>`, `COMPLETE 1`.
td_dump_report() {
  gzip -dc "$1" 2>/dev/null | awk '
    incopy {
      if ($0 == "\\.") { print "TABLE " table " " rows; incopy = 0 }
      else { rows++ }
      next
    }
    /^COPY public\./ {
      table = $2; sub(/^public\./, "", table); gsub(/"/, "", table)
      rows = 0; incopy = 1; next
    }
    /^CREATE TABLE public\./ {
      name = $3; sub(/^public\./, "", name); gsub(/"/, "", name)
      print "CREATED " name; next
    }
    /^-- PostgreSQL database dump complete/ { complete = 1 }
    END {
      # Незакрытый блок COPY — это обрыв дампа ровно на данных. Строку не печатаем:
      # такой блок не должен выглядеть как посчитанная таблица.
      if (complete && !incopy) print "COMPLETE 1"
    }
  '
}

# Отказ, если файл не полноценный дамп. Оборвавшийся pg_dump оставляет файл, который
# выглядит как бэкап: правильный размер, правильное имя, gzip местами читается.
td_verify_dump() {
  file="$1"
  report="$2"

  [ -s "$file" ] || td_die "$file пуст."
  gzip -t "$file" 2>/dev/null ||
    td_die "$file не распаковывается — архив повреждён или обрезан.
Восстанавливать из него нечего: это не бэкап, а его огрызок."

  td_dump_report "$file" >"$report" ||
    td_die "$file не удалось прочитать."

  grep -q '^COMPLETE 1$' "$report" ||
    td_die "В $file нет отметки об окончании дампа.
pg_dump до конца не дошёл: файл обрывается на середине данных. Такой файл
восстанавливать нельзя — часть строк в нём просто отсутствует."
}

# sha256 первым полем. На Windows sha256sum приезжает с Git for Windows.
td_sha256() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | cut -d' ' -f1
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | cut -d' ' -f1
  elif command -v openssl >/dev/null 2>&1; then
    openssl dgst -sha256 "$1" | sed 's/.*= *//'
  else
    td_die "Нечем посчитать sha256 — нужен sha256sum, shasum или openssl."
  fi
}

td_human_size() {
  if [ -f "$1" ]; then
    du -h "$1" 2>/dev/null | cut -f1 | tr -d ' \t'
  else
    echo "?"
  fi
}

# Подтверждение словом, а не «y». Скрипт, стирающий базу по одной букве, рано или поздно
# сотрёт её по случайно нажатой букве.
td_confirm() {
  word="$1"
  prompt="$2"
  if [ "${TD_ASSUME_YES:-}" = "1" ]; then
    td_say "$prompt"
    td_say "(--yes: подтверждение принято без вопроса)"
    return 0
  fi
  if [ ! -t 0 ]; then
    td_die "Нужно подтверждение, а ввод не с терминала.
Запустите вручную или передайте --yes, если понимаете, что делаете."
  fi
  td_say "$prompt"
  printf 'Введите %s, чтобы продолжить: ' "$word"
  read -r answer || answer=""
  [ "$answer" = "$word" ] || td_die "Введено не «$word» — ничего не сделано."
}
