#!/usr/bin/env sh
# `backup.bat|sh` — pg_dump в backups/td-<дата>.sql.gz, хранить последние 14 (SPEC.md 11.3).
#
# ⚠️ Бэкап, который нельзя восстановить, хуже отсутствия бэкапа: он создаёт уверенность,
# которой нет. Поэтому файл получает своё имя только после того, как проверен:
# пишем в скрытый .part, читаем обратно, сверяем с базой — и только потом переименовываем.
# Оборвавшийся pg_dump (кончился диск, docker убил контейнер) оставляет правдоподобный
# файл, и единственный способ это заметить — прочитать написанное.
#
# ⚠️ Дамп без .env бесполезен. Пароли брокерских счетов лежат в нём зашифрованными, а ключ
# (MASTER_KEY) живёт только в .env — про это скрипт говорит вслух каждый раз.
set -eu

TD_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$TD_ROOT"
. "$TD_ROOT/infra/scripts/common.sh"

# Сколько файлов остаётся после ротации (SPEC.md 11.3).
KEEP="${TD_BACKUP_KEEP:-14}"
BACKUP_DIR="$TD_ROOT/backups"

usage() {
  echo "Использование: infra/scripts/backup.sh [--quiet]" >&2
  echo "" >&2
  echo "  Снимает дамп базы в backups/td-<дата>.sql.gz, проверяет его и удаляет" >&2
  echo "  всё, кроме $KEEP последних по времени создания." >&2
}

QUIET=0
while [ $# -gt 0 ]; do
  case "$1" in
    --quiet) QUIET=1 ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "backup: неизвестный аргумент '$1'" >&2
      usage
      exit 2
      ;;
  esac
  shift
done

note() { [ "$QUIET" = "1" ] || td_say "$1"; }

td_require_installation
td_require_env
td_require_docker
td_ensure_postgres

# Дамп содержит зашифрованные пароли счетов и весь журнал. chmod после mv опоздал бы:
# всё время, пока pg_dump пишет .part, файл лежал бы с правами по умолчанию (0644),
# а снятие дампа большой базы — это не мгновение. umask действует на создание.
umask 077

mkdir -p "$BACKUP_DIR"

# Имя с датой, но никогда поверх существующего файла. Системная дата умеет уезжать назад
# (переустановка Windows, севшая батарейка), и тогда сегодняшнее имя совпадёт со вчерашним:
# перезапись означала бы, что бэкап уничтожил бэкап.
STAMP="$(date +%Y%m%d-%H%M%S)"
FINAL="$BACKUP_DIR/td-$STAMP.sql.gz"
suffix=2
while [ -e "$FINAL" ]; do
  FINAL="$BACKUP_DIR/td-$STAMP-$suffix.sql.gz"
  suffix=$((suffix + 1))
  [ "$suffix" -lt 100 ] || td_die "В $BACKUP_DIR не нашлось свободного имени для td-$STAMP."
done

# Точка с запятой в имени временного файла не нужна, а точка в начале нужна: недоделанный
# дамп не должен попадаться на глаза как «ещё один бэкап» и не должен попасть в ротацию.
PART="$BACKUP_DIR/.$(basename "$FINAL").part"
REPORT="$BACKUP_DIR/.$(basename "$FINAL").report"
PGSTATUS="$BACKUP_DIR/.$(basename "$FINAL").status"
# Хвосты прошлых прогонов: trap ловит INT и TERM, но не SIGKILL и не отключение питания.
# Ротация их не видит (она смотрит только td-*.sql.gz), поэтому копились бы они вечно.
rm -f "$BACKUP_DIR"/.td-*.part "$BACKUP_DIR"/.td-*.report "$BACKUP_DIR"/.td-*.status
rm -f "$PART" "$REPORT" "$PGSTATUS"
trap 'rm -f "$PART" "$REPORT" "$PGSTATUS"' EXIT INT TERM

# Что в базе сейчас — читаем ДО дампа, чтобы было с чем сверить написанное.
TABLES_BEFORE="$(td_psql "select tablename from pg_tables where schemaname = 'public' order by 1" |
  tr -d '\r')"

note "Снимаю дамп базы $TD_PG_DB…"

# --clean --if-exists: дамп сам сносит объекты перед созданием, поэтому restore не зависит
# от того, что сейчас в базе. --no-owner --no-privileges: роли на чужой машине другие.
#
# Код возврата pg_dump уносим отдельным файлом. Код конвейера — это код gzip, и он равен
# нулю даже когда pg_dump оборвался на середине: без этого файла бэкап рапортовал бы
# об успехе поверх обрезанного дампа. `set +e` вокруг обязателен: при set -e падение
# pg_dump убило бы подоболочку раньше, чем она успеет записать свой код.
set +e
{
  td_compose exec -T postgres \
    pg_dump -U "$TD_PG_USER" -d "$TD_PG_DB" --clean --if-exists --no-owner --no-privileges
  echo "$?" >"$PGSTATUS"
} | gzip -c >"$PART"
GZ_STATUS=$?
set -e

PG_STATUS="$(cat "$PGSTATUS" 2>/dev/null || echo "нет кода")"
[ "$PG_STATUS" = "0" ] ||
  td_die "pg_dump завершился с кодом $PG_STATUS — дамп не снят, файл удалён."
[ "$GZ_STATUS" = "0" ] ||
  td_die "gzip завершился с кодом $GZ_STATUS — дамп не сжат, файл удалён."

# Проверка написанного. Читаем файл обратно с диска, а не верим коду возврата.
td_verify_dump "$PART" "$REPORT"

# Каждая таблица, которая была в базе, обязана быть в дампе. Список фиксированных имён
# был бы слабее: он не заметит, что дамп обрезан ровно на последней таблице, и устареет
# на первой же миграции.
MISSING=""
for table in $TABLES_BEFORE; do
  grep -qx "CREATED $table" "$REPORT" || MISSING="$MISSING $table"
done
[ -z "$MISSING" ] ||
  td_die "В дампе нет таблиц, которые есть в базе:$MISSING
Файл удалён — это не бэкап."

mv "$PART" "$FINAL"
chmod 600 "$FINAL" 2>/dev/null || true

note ""
note "Готово: $FINAL ($(td_human_size "$FINAL"))"
if [ "$QUIET" != "1" ]; then
  ROWS="$(awk -v want=" $TD_COUNTED_TABLES " '
    $1 == "TABLE" && index(want, " " $2 " ") { printf "    %-20s %s\n", $2, $3 }
  ' "$REPORT")"
  if [ -n "$ROWS" ]; then
    note ""
    note "  Строк в дампе:"
    printf '%s\n' "$ROWS"
  fi
fi

# Путь к свежему бэкапу — файлом, а не в stdout: его читает update.sh, и мешать его
# с человеческим выводом значило бы поймать в переменную строку «Поднимаю postgres…».
[ -z "${TD_BACKUP_PATH_OUT:-}" ] || printf '%s\n' "$FINAL" >"$TD_BACKUP_PATH_OUT"

## ----------------------------------------------------------------------------
## Ротация
## ----------------------------------------------------------------------------

# Логика — td_rotate_backups в common.sh: в $KEEP засчитываются только файлы, которые
# распаковываются, а созданный этим прогоном защищён отдельно. Здесь только --quiet:
# сообщения об удалении глушатся, предупреждение о нераспаковываемых файлах идёт
# в stderr и не глушится ничем — это находка, а не рутина.
if [ "$QUIET" = "1" ]; then
  td_rotate_backups "$BACKUP_DIR" "$KEEP" "$FINAL" >/dev/null
else
  td_rotate_backups "$BACKUP_DIR" "$KEEP" "$FINAL"
fi

note ""
note "⚠️  Дамп без .env бесполезен: пароли счетов в нём зашифрованы MASTER_KEY, а ключ"
note "    лежит только в .env. Храните копию .env рядом с бэкапами."
