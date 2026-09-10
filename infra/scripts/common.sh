#!/usr/bin/env sh
# Общая часть скриптов установки (SPEC.md 11.3). Сам по себе не запускается — только
# `. common.sh` из скрипта, который уже определил TD_ROOT.
#
# Почему отдельный файл: скрипты делают одно и то же с .env, docker и postgres, и
# расхождение этих кусков стоило бы данных. `.bat`-обёртки логики не содержат вовсе
# (см. start.bat) — значит, версия на Windows и на macOS ровно одна, и разойтись им негде.
#
# init-env.sh и stop.sh берут отсюда только td_cmd и печать (X-64): своя копия определения
# платформы в каждом скрипте разошлась бы ровно так же молча, как разошлись бы .bat и .sh.
#
# ⚠️ Значения секретов из .env здесь не читаются и не печатаются никогда. MASTER_KEY
# проверяется только на присутствие (`td_env_present`), а его отпечаток считает контейнер
# api из своего env_file — в переменную shell ключ не попадает ни на секунду.

# Профиль compose. `local` — установка у тестировщика, `prod` — вариант с caddy.
PROFILE="${PROFILE:-local}"

# Таблицы, чьи счётчики человек видит перед восстановлением. Это тот самый слой, который
# нигде больше не хранится: брокер помнит сделки, рефлексии не помнит никто.
TD_COUNTED_TABLES="users trading_accounts deals positions journal_entries reflections tags attachments"

# printf, а не echo: `sh` на macOS (bash в posix-режиме) и `sh` на Debian (dash) обе
# разворачивают escape-последовательности в echo, и путь вида C:\tradedesk человек увидел
# бы как «C:» и табуляцию. Проверено: `sh -c 'echo "a\tb"'` печатает табуляцию.
td_die() {
  printf '\n%s\n' "$1" >&2
  exit "${2:-1}"
}

td_say() {
  printf '%s\n' "$1"
}

# То, что человек обязан увидеть, даже когда вывод скрипта заглушён (`backup --quiet`).
td_warn() {
  printf '%s\n' "$1" >&2
}

# Windows ли под нами. Git Bash отвечает MINGW64_NT-…, MSYS_NT-… или CYGWIN_NT-…;
# OS=Windows_NT приезжает из самой Windows и в Git Bash сохраняется — второй признак нужен
# на случай, если uname в PATH не окажется вовсе.
td_is_windows() {
  case "$(uname -s 2>/dev/null || true)" in
    MINGW* | MSYS* | CYGWIN*) return 0 ;;
  esac
  [ "${OS:-}" = "Windows_NT" ]
}

# Как называется действие там, где человек стоит: init | up | down | backup | restore |
# update. Одной строкой на обе платформы не обойтись — `make` на Windows не ставится и по
# SETUP.md §1 не нужен, а `.bat` бессмысленны на macOS.
#
# ⚠️ X-64. Скрипт — единственный источник, который человек читает В МОМЕНТ действия, и он
# ведёт его дальше по установке. Совет выполнить несуществующую команду здесь дороже той же
# неточности в документе: до документа человек ещё дойдёт, а окно у него перед глазами уже
# сейчас. Найдено на живой машине: «Дальше: make up» в окне init.bat.
#
# Имена совпадают с SETUP.md дословно — там то же действие называется `infra\scripts\start.bat`.
td_cmd() {
  if td_is_windows; then
    case "$1" in
      init) printf '%s\n' 'infra\scripts\init.bat' ;;
      up) printf '%s\n' 'infra\scripts\start.bat' ;;
      down) printf '%s\n' 'infra\scripts\stop.bat' ;;
      backup) printf '%s\n' 'infra\scripts\backup.bat' ;;
      restore) printf '%s\n' 'infra\scripts\restore.bat' ;;
      update) printf '%s\n' 'infra\scripts\update.bat' ;;
      *) printf '%s\n' "$1" ;;
    esac
  else
    case "$1" in
      restore) printf '%s\n' 'make restore file=…' ;;
      init | up | down | backup | update) printf '%s\n' "make $1" ;;
      *) printf '%s\n' "$1" ;;
    esac
  fi
}

# Сам файл скрипта — для строк «Использование: …». Отличается от td_cmd тем, что несёт
# флаги: `make backup` не умеет --quiet (цель зовёт скрипт без аргументов), а backup.bat
# умеет — он отдаёт %* внутрь.
#
# ⚠️ Годятся только имена, у которых пара .sh/.bat сходится: start, stop, backup, restore,
# update. init-env.sh на Windows называется init.bat, и «init-env» здесь дало бы путь к
# файлу, которого нет. За этим следит сторож в test-scripts.sh.
td_script() {
  if td_is_windows; then
    printf '%s\n' "infra\\scripts\\$1.bat"
  else
    printf '%s\n' "infra/scripts/$1.sh"
  fi
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

# Есть ли в строке байт вне печатной латиницы (0x20…0x7E). LC_ALL=C обязателен: без него
# диапазон «пробел…тильда» зависит от порядка сортировки локали и кириллица в него попадает.
#
# Вычитание диапазона, а не grep: grep работает построчно и путь с переводом строки внутри
# пропустил бы — каждая строка по отдельности печатна, а в имени файла Unix запрещает только
# «/» и NUL. Хвостовой «x» нужен, чтобы подстановка команды не съела оставшийся перевод
# строки вместе с ответом.
td_path_non_ascii() {
  [ "$(printf '%s' "$1" | LC_ALL=C tr -d ' -~'; printf x)" != x ]
}

# ⚠️ X-54. Ломает не кириллица сама по себе, а пара «не-ASCII + сборка нескольких образов
# за один запуск». На несколько образов сразу Docker открывает одну общую сессию, ключ
# которой берёт из имени папки проекта и шлёт в HTTP-заголовке; не-ASCII в заголовке
# недопустим, и всё обрывается ДО начала сборки. У нас образов всегда больше одного
# (profile local — api и worker, prod — ещё и web), так что попадание гарантировано.
# Ошибка при этом говорит про gRPC и заголовки, но ни папку, ни причину не называет —
# поэтому путь проверяется до compose, а не после.
#
# Матрица, прогнанная на macOS (Docker 29.6.1, Compose v5.3.0):
#   папка «tradedesk-тест», два образа            падает
#   она же, один образ                            собирается
#   кириллица только в РОДИТЕЛЬСКИХ папках        собирается
#   имя папки целиком кириллицей                  compose падает раньше и по другой
#                                                 причине: «project name must not be empty»
#   COMPOSE_BAKE=false и COMPOSE_BAKE=0           НЕ помогает, падает так же
#   DOCKER_BUILDKIT=0                             собирается
#
# Проверка при этом смотрит на путь ЦЕЛИКОМ и потому строже измеренного: на Windows путь
# устроен иначе (\\?\C:\…), там это не прогонялось (T-06), и делить путь на «имя папки» и
# «родителей» по результатам macOS мы не будем. Цена ошибки несимметрична: лишний отказ
# человек читает словами и переносит папку, пропущенный случай отдаёт ему ошибку про gRPC.
#
# Обход существует сегодня, и он из двух переменных сразу:
#   TD_ALLOW_NON_ASCII_PATH=1 DOCKER_BUILDKIT=0 sh infra/scripts/start.sh
# одной первой мало — она снимает только нашу проверку, а падает Docker; одной второй мало —
# до Docker дело не дойдёт, эта проверка сработает раньше. Ставить DOCKER_BUILDKIT=0 за
# человека мы не стали: классический сборщик не видит кэш BuildKit (первая сборка заметно
# дольше), и Docker объявил его устаревшим — держать на нём штатный путь установки значит
# копить долг.
td_require_ascii_path() {
  td_path_non_ascii "$TD_ROOT" || return 0
  if [ "${TD_ALLOW_NON_ASCII_PATH:-}" = "1" ]; then
    td_warn "TD_ALLOW_NON_ASCII_PATH=1: в пути есть не-латинские символы, проверка снята."
    return 0
  fi
  td_die "В пути к папке установки есть символы, которые Docker не понимает:

    $TD_ROOT

Сборка оборвётся раньше, чем начнётся. TradeDesk собирает несколько образов за один
запуск, и на такую сборку Docker открывает общую сессию, имя которой берёт из пути
к папке и передаёт в служебном заголовке — а там допустимы только латинские буквы,
цифры и знаки препинания. Ошибка выглядит как «failed to dial gRPC … header key
\"x-docker-expose-session-sharedkey\" contains value with non-printable ASCII
characters» и про папку не говорит ни слова.

Перенесите папку установки туда, где в пути только латиница, и запустите снова:
    Windows   C:\\tradedesk
    macOS     /Users/Shared/tradedesk
    Linux     ~/tradedesk
Путь к домашней папке (~) годится не всегда: если имя вашей учётной записи написано
по-русски, оно тоже часть пути.

Переносите папку целиком, вместе со скрытым файлом .env и каталогом backups:
в .env лежит MASTER_KEY, без которого пароли брокерских счетов не расшифровать.

Если перенести папку нельзя, есть обход — обе переменные сразу, из терминала или
Git Bash, в папке установки:
    TD_ALLOW_NON_ASCII_PATH=1 DOCKER_BUILDKIT=0 sh infra/scripts/start.sh
Он включает старый сборщик Docker: заголовка с путём тот не шлёт, но и кэш нового
сборщика не видит — первая сборка будет заметно дольше. Проверено на macOS."
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
      # restarting — это цикл перезапусков, а не «ещё стартует». Без него контейнер,
      # падающий и поднимающийся заново, выбирал бы все 120 секунд и только потом
      # сказал бы правду. Список тот же, что в start.sh.
      restarting | exited | dead | paused | removing | missing)
        td_compose logs --tail 25 postgres >&2 2>/dev/null || true
        td_die "postgres не запустился (состояние: $state)."
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

# Таблицы, без которых файл — не дамп TradeDesk. Все четыре заведены первой же миграцией
# (b07a46275bbc), поэтому их отсутствие означает чужую базу, а не старую версию нашей.
# Без этой проверки дамп соседнего проекта проходил бы по одному наличию CREATE TABLE,
# и его таблицы доливались бы в базу журнала.
TD_REQUIRED_TABLES="users trading_accounts deals positions"

td_dump_looks_like_tradedesk() {
  report="$1"
  missing=""
  for table in $TD_REQUIRED_TABLES; do
    grep -qx "CREATED $table" "$report" || missing="$missing $table"
  done
  printf '%s' "${missing# }"
}

# Таблицы, которые есть в базе, но которых в дампе нет вовсе. Дамп с --clean сносит только
# то, что в нём есть, — такие таблицы восстановление не тронет. Разница с «в дампе 0 строк»
# принципиальная: там строки исчезнут, здесь останутся.
#
# $1 — файл «имя<TAB>строк» (вывод td_table_counts), $2 — отчёт td_dump_report.
td_dump_absent_tables() {
  while IFS="$(printf '\t')" read -r table count <&3; do
    [ -n "$table" ] || continue
    grep -qx "CREATED $table" "$2" || printf '%s\n' "$table"
  done 3<"$1"
}

# Строки таблицы «сейчас в базе / станет из бэкапа». Отдельной функцией, потому что это
# единственное, что человек видит перед необратимой операцией: врущий здесь столбец
# дороже любого другого вывода в проекте, и он проверяется тестом без докера.
#
# $1 — файл «имя<TAB>строк», $2 — отчёт td_dump_report.
td_restore_preview() {
  while IFS="$(printf '\t')" read -r table count <&3; do
    [ -n "$table" ] || continue
    if grep -qx "CREATED $table" "$2"; then
      from_dump="$(awk -v t="$table" '$1 == "TABLE" && $2 == t { print $3 }' "$2")"
      [ -n "$from_dump" ] || from_dump=0
      mark=" "
      [ "$from_dump" -ge "$count" ] 2>/dev/null || mark="←"
      printf '  %s %-20s %13s   %s\n' "$mark" "$table" "$count" "$from_dump"
    else
      printf '  %s %-20s %13s   %s\n' " " "$table" "$count" "останется как есть"
    fi
  done 3<"$1"
}

# Значения key_version из блока COPY public.account_credentials — отпечатки ключа, которым
# зашифрованы пароли счетов в этом дампе (ADR-0003). Номер колонки читается из заголовка
# COPY, а не константой: порядок колонок задаёт pg_dump, и миграция его меняет.
#
# Разбор — тем же конечным автоматом, что и td_dump_report: заголовки COPY распознаются
# только вне блока данных. Иначе заметка пользователя, начинающаяся со слов
# «COPY public.account_credentials (…) FROM stdin;», открыла бы поддельный блок и подсунула
# бы свои «отпечатки» — то есть решала бы за скрипт, тем ли ключом зашифрован бэкап.
td_dump_key_versions() {
  gzip -dc "$1" 2>/dev/null | awk '
    BEGIN { FS = "\t"; idx = 0; incopy = 0; want = 0 }
    incopy {
      if ($0 == "\\.") { incopy = 0; want = 0; next }
      if (want && idx > 0 && $idx != "") print $idx
      next
    }
    /^COPY public\./ {
      incopy = 1; want = 0; idx = 0
      name = $0
      sub(/^COPY public\./, "", name)
      sub(/[ (].*$/, "", name)
      gsub(/"/, "", name)
      if (name != "account_credentials") next
      want = 1
      cols = $0
      sub(/^[^(]*\(/, "", cols)
      sub(/\).*$/, "", cols)
      n = split(cols, arr, /,/)
      for (i = 1; i <= n; i++) {
        col = arr[i]
        gsub(/[" \t]/, "", col)
        if (col == "key_version") idx = i
      }
      next
    }
  ' | sort -u
}

# Отпечаток текущего MASTER_KEY (и предыдущего, если задан) — считает контейнер api тем же
# кодом, что шифрует данные. Ключ приезжает туда через env_file и в shell не попадает
# вовсе: ни в переменную, ни в список процессов, ни в вывод.
#
# Печатает «cur <n>» и, если задан MASTER_KEY_PREVIOUS, «prev <n>». Ненулевой код — не
# смогли посчитать; что делать дальше, решает вызывающий: update отказывается, restore
# продолжает с оговоркой.
TD_PY_FINGERPRINT='
import os
import sys

from app.core.security import key_fingerprint, parse_master_key

current = os.environ.get("MASTER_KEY", "").strip()
if not current:
    sys.exit("MASTER_KEY пуст")
print("cur %d" % key_fingerprint(parse_master_key(current, variable="MASTER_KEY")))
previous = os.environ.get("MASTER_KEY_PREVIOUS", "").strip()
if previous:
    print("prev %d" % key_fingerprint(
        parse_master_key(previous, variable="MASTER_KEY_PREVIOUS")))
'

td_key_fingerprints() {
  fp_err="$(mktemp "${TMPDIR:-/tmp}/td-fp.XXXXXX")"
  if ! fp_out="$(td_compose run --rm --no-deps -T --entrypoint python api \
    -c "$TD_PY_FINGERPRINT" 2>"$fp_err")"; then
    sed 's/^/      /' "$fp_err" >&2
    rm -f "$fp_err"
    return 1
  fi
  rm -f "$fp_err"
  printf '%s\n' "$fp_out"
}

# Сверка отпечатков: $1 — текущий, $2 — предыдущий (может быть пуст), дальше — отпечатки,
# найденные в базе или в дампе. Печатает одну строку «<вердикт><TAB><чужие отпечатки>»:
#
#   none      сверять не с чем — ни одного отпечатка не передано
#   current   всё зашифровано текущим ключом
#   previous  всё на предыдущем ключе: ротация начата и не закончена
#   unknown   есть отпечатки, которых нет ни в одном ключе из .env — ключ чужой
#
# Чистая функция без докера: это самая дорогая логика задачи, и она обязана быть под тестом.
td_key_verdict() {
  kv_cur="$1"
  kv_prev="$2"
  shift 2
  kv_unknown=""
  kv_matched=0
  kv_any=0
  for kv in "$@"; do
    [ -n "$kv" ] || continue
    kv_any=1
    if [ "$kv" = "$kv_cur" ]; then
      kv_matched=1
    elif [ -n "$kv_prev" ] && [ "$kv" = "$kv_prev" ]; then
      :
    else
      kv_unknown="$kv_unknown $kv"
    fi
  done
  if [ "$kv_any" = "0" ]; then
    printf 'none\t\n'
  elif [ -n "$kv_unknown" ]; then
    printf 'unknown\t%s\n' "${kv_unknown# }"
  elif [ "$kv_matched" = "1" ]; then
    printf 'current\t\n'
  else
    printf 'previous\t\n'
  fi
}

# Версия пакета из тега: 'v' не входит, '-rc1' пишется как 'rc1' (PEP 440).
# Ровно то же преобразование делает infra/scripts/make-release.sh.
td_tag_to_version() {
  printf '%s' "${1#v}" | sed 's/-rc/rc/'
}

# Тег из имени архива: tradedesk-0.2.0.zip → v0.2.0. Имя ничего не доказывает — версию
# внутри архива update сверяет отдельно, уже после распаковки.
td_zip_to_tag() {
  printf 'v%s' "$(basename "$1" .zip | sed 's/^tradedesk-//')"
}

# tag_name из ответа GitHub. Разбор без jq и без python: на машине пользователя нет ни
# того, ни другого. `head -1` достаточно, потому что tag_name идёт раньше body, где текст
# релиза мог бы содержать такую же строку.
td_parse_tag_name() {
  tr ',' '\n' <"$1" |
    sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' |
    head -1
}

# Ротация: оставить последние $2 целых бэкапов в каталоге $1, не трогая файл $3.
#
# Считаем по времени изменения (`ls -t`), а не по имени: имя с датой врёт, если системная
# дата уехала, и сортировка по нему удалила бы свежий файл вместо старого.
#
# В $2 засчитываются только файлы, которые распаковываются. Иначе достаточно положить
# в backups/ два десятка пустых td-*.sql.gz, чтобы следующий прогон удалил все настоящие
# копии и оставил мусор: имя ничего не доказывает, а ротация удаляет. Мусор при этом не
# удаляется — он назван вслух: право сносить чужие файлы по несовпадению формата скрипт
# себе не берёт.
#
# Файл с датой из будущего сортируется первым и ротацию переживает всегда. Так и оставлено:
# он занимает одно место из $2, но это дешевле, чем удалять бэкап по подозрению к его mtime.
td_rotate_backups() {
  rot_dir="$1"
  rot_keep="$2"
  rot_protect="${3:-}"
  [ "${rot_keep:-0}" -gt 0 ] || return 0

  rot_list="$(mktemp "${TMPDIR:-/tmp}/td-rot.XXXXXX")"
  rot_bad="$(mktemp "${TMPDIR:-/tmp}/td-rotbad.XXXXXX")"
  ls -t "$rot_dir"/td-*.sql.gz >"$rot_list" 2>/dev/null || true

  rot_kept=0
  rot_removed=0
  while IFS= read -r rot_file <&3; do
    [ -n "$rot_file" ] || continue
    [ -f "$rot_file" ] || continue
    if ! gzip -t "$rot_file" 2>/dev/null; then
      basename "$rot_file" >>"$rot_bad"
      continue
    fi
    if [ "$rot_kept" -lt "$rot_keep" ]; then
      rot_kept=$((rot_kept + 1))
      continue
    fi
    [ "$rot_file" != "$rot_protect" ] || continue
    rm -f "$rot_file"
    rot_removed=$((rot_removed + 1))
    td_say "  удалён старый бэкап: $(basename "$rot_file")"
  done 3<"$rot_list"

  if [ "$rot_removed" != "0" ]; then
    td_say ""
    td_say "Оставлено последних целых бэкапов: $rot_kept."
  fi

  if [ -s "$rot_bad" ]; then
    td_warn ""
    td_warn "⚠️  В $rot_dir лежат файлы с именем бэкапа, которые не распаковываются:"
    sed 's/^/      /' "$rot_bad" >&2
    td_warn "    Это не бэкапы. Ротация их не считает и не удаляет — разберитесь сами."
  fi

  rm -f "$rot_list" "$rot_bad"
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
