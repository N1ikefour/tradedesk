#!/usr/bin/env sh
# `make test-scripts` — проверка того, чем backup и restore отличают целый дамп от огрызка.
#
# Почему именно это место покрыто тестом, а не скрипты целиком. `backup.sh` и `restore.sh`
# без Postgres не запускаются, и гонять docker в гейте мы не будем. Но вся их безопасность
# держится на двух функциях из common.sh — `td_dump_report` и `td_verify_dump`, — и они
# чистые: файл на входе, вердикт на выходе. Именно они стоят между человеком и бэкапом,
# который выглядит как бэкап, но восстанавливается наполовину.
#
# Разбор блока COPY конечным автоматом тоже проверяется здесь: в дампе лежат заметки
# пользователя, и строка «COPY public.positions (…) FROM stdin;» внутри рефлексии — не
# выдумка, а то, что человек напишет, разбираясь, почему у него что-то не сошлось.
set -eu

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TD_ROOT="$ROOT"
. "$ROOT/infra/scripts/common.sh"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/tdverify.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT INT TERM

FAILED=0

ok() { echo "  ok    $1"; }
bad() {
  echo "  ПРОВАЛ $1" >&2
  FAILED=1
}

# td_die завершает процесс, поэтому отказ проверяется в подоболочке.
expect_reject() {
  name="$1"
  file="$2"
  if (td_verify_dump "$file" "$WORK/report.out") >"$WORK/out" 2>&1; then
    bad "$name — файл принят, а должен был быть отвергнут"
  else
    ok "$name"
  fi
}

expect_accept() {
  name="$1"
  file="$2"
  if (td_verify_dump "$file" "$WORK/report.out") >"$WORK/out" 2>&1; then
    ok "$name"
  else
    bad "$name — целый дамп отвергнут:"
    sed 's/^/        /' "$WORK/out" >&2
  fi
}

## ----------------------------------------------------------------------------
## Образец дампа. Форма — та же, что у pg_dump --clean --if-exists.
## ----------------------------------------------------------------------------

cat >"$WORK/full.sql" <<'SQL'
--
-- PostgreSQL database dump
--

DROP TABLE IF EXISTS public.reflections;
CREATE TABLE public.positions (
    id uuid NOT NULL,
    symbol_norm text NOT NULL
);
CREATE TABLE public.journal_entries (
    position_id uuid NOT NULL,
    notes text
);
CREATE TABLE public.reflections (
    position_id uuid NOT NULL,
    free_text text
);

COPY public.positions (id, symbol_norm) FROM stdin;
11111111-1111-1111-1111-111111111111	EURUSD
22222222-2222-2222-2222-222222222222	XAUUSD
\.

COPY public.journal_entries (position_id, notes) FROM stdin;
11111111-1111-1111-1111-111111111111	COPY public.positions (id, symbol_norm) FROM stdin;
22222222-2222-2222-2222-222222222222	CREATE TABLE public.deals (id uuid);
\.

COPY public.reflections (position_id, free_text) FROM stdin;
11111111-1111-1111-1111-111111111111	не двигать стоп руками
\.

--
-- PostgreSQL database dump complete
--
SQL

gzip -c <"$WORK/full.sql" >"$WORK/full.sql.gz"

echo "test-backup-verify: проверка распознавания целого и битого дампа"
echo ""

## ----------------------------------------------------------------------------

expect_accept "целый дамп принимается" "$WORK/full.sql.gz"

REPORT="$WORK/report.full"
td_dump_report "$WORK/full.sql.gz" >"$REPORT"

for table in positions journal_entries reflections; do
  grep -qx "CREATED $table" "$REPORT" ||
    bad "в отчёте нет CREATED $table"
done
grep -qx "CREATED $table" "$REPORT" && ok "все три CREATE TABLE найдены"

grep -qx "COMPLETE 1" "$REPORT" || bad "не найдена отметка об окончании дампа"
grep -qx "COMPLETE 1" "$REPORT" && ok "отметка об окончании дампа найдена"

# Главное свойство разбора: строки внутри COPY — данные, а не разметка. Заметка
# пользователя со словами «COPY public.positions … FROM stdin;» обязана посчитаться
# одной строкой journal_entries, а не открыть второй блок positions.
counts="$(awk '$1 == "TABLE" { print $2 "=" $3 }' "$REPORT" | sort | tr '\n' ' ')"
expected="journal_entries=2 positions=2 reflections=1 "
if [ "$counts" = "$expected" ]; then
  ok "строки внутри COPY посчитаны верно: $counts"
else
  bad "счётчики строк разошлись: получили «$counts», ждали «$expected»"
fi

# И CREATE TABLE внутри данных не должен добавить несуществующую таблицу.
if grep -qx "CREATED deals" "$REPORT"; then
  bad "CREATE TABLE из текста заметки принят за настоящую таблицу"
else
  ok "CREATE TABLE внутри данных не принят за таблицу"
fi

## ----------------------------------------------------------------------------
## Формы порчи
## ----------------------------------------------------------------------------

: >"$WORK/empty.sql.gz"
expect_reject "пустой файл отвергнут" "$WORK/empty.sql.gz"

head -c 40 "$WORK/full.sql.gz" >"$WORK/cut-gzip.sql.gz"
expect_reject "оборванный gzip отвергнут" "$WORK/cut-gzip.sql.gz"

printf 'это вообще не gzip\n' >"$WORK/plain.sql.gz"
expect_reject "не-gzip отвергнут" "$WORK/plain.sql.gz"

# Самая опасная форма: gzip целый, дамп оборван на данных. Файл открывается, таблицы
# в нём есть, а части строк нет — и заметить это можно только по отсутствию отметки.
sed '/^COPY public.reflections/,$d' "$WORK/full.sql" | gzip -c >"$WORK/cut-sql.sql.gz"
expect_reject "дамп без отметки об окончании отвергнут" "$WORK/cut-sql.sql.gz"

# Обрыв ровно посреди блока COPY, но с отметкой в конце — так выглядел бы дамп,
# склеенный из двух кусков. Незакрытый блок обязан отменять отметку.
{
  sed '/^COPY public.reflections/q' "$WORK/full.sql"
  echo "11111111-1111-1111-1111-111111111111	оборвалось здесь"
  echo "--"
  echo "-- PostgreSQL database dump complete"
} | gzip -c >"$WORK/unclosed.sql.gz"
expect_reject "незакрытый блок COPY отвергнут" "$WORK/unclosed.sql.gz"

echo ""
if [ "$FAILED" = "0" ]; then
  echo "test-backup-verify: всё сошлось."
else
  echo "test-backup-verify: есть провалы." >&2
  exit 1
fi
