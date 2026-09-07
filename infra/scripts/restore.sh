#!/usr/bin/env sh
# `restore.bat|sh <файл>` — восстановление базы из бэкапа (SPEC.md 11.3).
#
# ⚠️ Это единственная деструктивная операция в проекте, направленная на живую базу.
# Отсюда весь порядок ниже:
#
# 1. Файл проверяется ДО того, как что-то трогается. Наполовину восстановленная база
#    хуже нетронутой: человек увидит журнал, в котором чего-то нет, и не поймёт чего.
# 2. Человеку показывается, что именно он теряет — счётчики текущей базы против
#    счётчиков внутри бэкапа, — и только потом спрашивается подтверждение.
# 3. Перед перезаписью снимается ещё один бэкап. Ошибиться файлом — самый вероятный
#    способ потерять данные этой командой, и он должен быть обратим.
# 4. Заливка идёт одной транзакцией с ON_ERROR_STOP: либо применилось всё, либо ничего.
set -eu

TD_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$TD_ROOT"
. "$TD_ROOT/infra/scripts/common.sh"

usage() {
  echo "Использование: infra/scripts/restore.sh <backups/td-….sql.gz> [--yes]" >&2
  echo "" >&2
  echo "  Заменяет содержимое базы данными из бэкапа." >&2
  echo "  --yes — не спрашивать подтверждения (для неинтерактивного запуска)." >&2
  echo "" >&2
  echo "Доступные бэкапы:" >&2
  available="$(ls -t "$TD_ROOT"/backups/td-*.sql.gz 2>/dev/null || true)"
  if [ -n "$available" ]; then
    printf '%s\n' "$available" | sed 's|^|      |' >&2
  else
    echo "      (в backups/ пусто — снимите копию: make backup)" >&2
  fi
}

FILE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --yes) TD_ASSUME_YES=1 ;;
    -h | --help)
      usage
      exit 0
      ;;
    -*)
      echo "restore: неизвестный аргумент '$1'" >&2
      usage
      exit 2
      ;;
    *)
      [ -z "$FILE" ] || {
        echo "restore: файл указывается один." >&2
        exit 2
      }
      FILE="$1"
      ;;
  esac
  shift
done

[ -n "$FILE" ] || {
  usage
  exit 2
}
[ -f "$FILE" ] || td_die "Файл не найден: $FILE"
FILE="$(cd "$(dirname "$FILE")" && pwd)/$(basename "$FILE")"

td_require_installation
td_require_env
td_require_docker

## ----------------------------------------------------------------------------
## Проверка файла — до того, как тронута база
## ----------------------------------------------------------------------------

REPORT="$(mktemp "${TMPDIR:-/tmp}/td-restore.XXXXXX")"
trap 'rm -f "$REPORT"' EXIT INT TERM

td_say "Проверяю $FILE…"
td_verify_dump "$FILE" "$REPORT"
grep -q '^CREATED ' "$REPORT" ||
  td_die "В $FILE нет ни одной таблицы. Это не дамп базы TradeDesk."

td_ensure_postgres

## ----------------------------------------------------------------------------
## Что именно перезаписываем
## ----------------------------------------------------------------------------

NOW="$(td_table_counts)"

td_say ""
td_say "==============================================================="
td_say " ЧТО БУДЕТ ПЕРЕЗАПИСАНО"
td_say "==============================================================="
td_say ""
td_say "  База      $TD_PG_DB (том td_pgdata, контейнер postgres)"
td_say "  Из файла  $FILE"
td_say "  Размер    $(td_human_size "$FILE")"
td_say "  Дата      $(date -r "$FILE" '+%Y-%m-%d %H:%M:%S' 2>/dev/null ||
  stat -c '%y' "$FILE" 2>/dev/null || echo '?')"
td_say ""
td_say "    Таблица             сейчас в базе   станет из бэкапа"
printf '%s\n' "$NOW" | while IFS="$(printf '\t')" read -r table count; do
  [ -n "$table" ] || continue
  from_dump="$(awk -v t="$table" '$1 == "TABLE" && $2 == t { print $3 }' "$REPORT")"
  # Таблица есть в базе, но в дампе её блока COPY нет — значит, она станет пустой.
  [ -n "$from_dump" ] || from_dump=0
  mark=" "
  [ "$from_dump" -ge "$count" ] 2>/dev/null || mark="←"
  printf '  %s %-20s %13s   %s\n' "$mark" "$table" "$count" "$from_dump"
done
td_say ""
td_say "  «←» — строк станет меньше, чем сейчас. Разница будет потеряна."
td_say ""
td_say "  MASTER_KEY из .env НЕ трогается и НЕ восстанавливается: он лежит в файле,"
td_say "  а не в базе. Если .env с тех пор менялся, пароли счетов из бэкапа не"
td_say "  расшифруются — это отдельная проблема, и restore её не решает."
td_say ""

td_confirm "restore" "Продолжить? Текущее содержимое базы будет заменено."

## ----------------------------------------------------------------------------
## Страховка: бэкап того, что сейчас
## ----------------------------------------------------------------------------

# Ошибиться файлом — самый вероятный способ потерять данные этой командой. Свежий дамп
# перед перезаписью делает ошибку обратимой; без него «восстановил не то» необратимо.
td_say ""
td_say "Сначала — бэкап текущего состояния, на случай если файл выбран не тот."
SAFETY_OUT="$(mktemp "${TMPDIR:-/tmp}/td-safety.XXXXXX")"
TD_BACKUP_PATH_OUT="$SAFETY_OUT" "$TD_ROOT/infra/scripts/backup.sh" ||
  td_die "Страховочный бэкап не снялся — восстановление отменено, база не тронута."
SAFETY="$(cat "$SAFETY_OUT")"
rm -f "$SAFETY_OUT"

## ----------------------------------------------------------------------------
## Заливка
## ----------------------------------------------------------------------------

# api и worker держат соединения и получили бы DROP TABLE под собой. Гасим их, но не
# postgres: заливать некуда, если погасить и его.
td_say ""
td_say "Останавливаю api и worker на время заливки…"
td_compose stop api worker >/dev/null 2>&1 || true

# --single-transaction + ON_ERROR_STOP: либо применилось всё, либо база осталась прежней.
# Без этого битый дамп оставил бы половину таблиц восстановленными, а половину — нет,
# и разницу никто бы не заметил до первого открытого экрана.
td_say "Заливаю дамп одной транзакцией…"
set +e
gzip -dc "$FILE" | td_compose exec -T postgres \
  psql -X -q -v ON_ERROR_STOP=1 --single-transaction \
  -U "$TD_PG_USER" -d "$TD_PG_DB" >/dev/null
PSQL_STATUS=$?
set -e

if [ "$PSQL_STATUS" != "0" ]; then
  td_say ""
  td_say "Поднимаю api и worker обратно…"
  td_compose up -d >/dev/null 2>&1 || true
  td_die "psql завершился с кодом $PSQL_STATUS — транзакция откачена, база НЕ изменена.
Страховочный бэкап на месте: $SAFETY"
fi

td_say ""
td_say "Поднимаю приложение…"
"$TD_ROOT/infra/scripts/start.sh" || td_die "Данные восстановлены, но приложение не поднялось.
Смотрите: docker compose logs api"

td_ensure_postgres
td_say ""
td_say "Восстановлено. Сейчас в базе:"
td_table_counts | td_print_counts
td_say ""
td_say "Состояние до восстановления сохранено здесь: $SAFETY"
