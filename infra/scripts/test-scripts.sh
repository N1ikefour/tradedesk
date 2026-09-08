#!/usr/bin/env sh
# `make test-scripts` — проверка того, на чём держатся backup, restore и update (T-02).
#
# Почему тестируются функции, а не скрипты целиком. `backup.sh`, `restore.sh` и `update.sh`
# без Postgres и без докера не запускаются, и гонять докер в гейте мы не будем. Но всё, чем
# они отличают целое от испорченного, вынесено в common.sh чистыми функциями: файл или
# строки на входе — вердикт на выходе. Именно они стоят между человеком и потерянным
# журналом, поэтому под тестом здесь ровно они:
#
#   td_verify_dump / td_dump_report   целый дамп против огрызка
#   td_dump_looks_like_tradedesk      наш дамп против чужого
#   td_restore_preview                таблица «что будет перезаписано» — то единственное,
#                                     что человек видит перед необратимой операцией
#   td_dump_absent_tables             таблицы, которых в дампе нет вовсе
#   td_dump_key_versions              отпечатки ключа внутри бэкапа
#   td_key_verdict                    сверка MASTER_KEY — самая дорогая логика задачи
#   td_rotate_backups                 ротация, которая удаляет файлы
#   td_tag_to_version / td_zip_to_tag / td_parse_tag_name   разбор версии и ответа GitHub
#
# Что остаётся непокрытым и почему: сам перенос файлов, метка незавершённого обновления,
# сборка образов и сверка версии с ответом /api/v1/version — им нужен докер и настоящий
# релиз, они проверяются прогоном руками (см. SETUP.md, раздел «Не проверено»).
set -eu

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TD_ROOT="$ROOT"
. "$ROOT/infra/scripts/common.sh"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/tdscripts.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT INT TERM

FAILED=0

ok() { echo "  ok    $1"; }
bad() {
  echo "  ПРОВАЛ $1" >&2
  FAILED=1
}

same() {
  # $1 — что проверяем, $2 — получили, $3 — ждали.
  if [ "$2" = "$3" ]; then
    ok "$1"
  else
    bad "$1: получили «$2», ждали «$3»"
  fi
}

# td_die завершает процесс, поэтому отказ проверяется в подоболочке.
expect_reject() {
  if (td_verify_dump "$2" "$WORK/report.out") >"$WORK/out" 2>&1; then
    bad "$1 — файл принят, а должен был быть отвергнут"
  else
    ok "$1"
  fi
}

expect_accept() {
  if (td_verify_dump "$2" "$WORK/report.out") >"$WORK/out" 2>&1; then
    ok "$1"
  else
    bad "$1 — целый дамп отвергнут:"
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
CREATE TABLE public.users (
    id uuid NOT NULL
);
CREATE TABLE public.trading_accounts (
    id uuid NOT NULL
);
CREATE TABLE public.deals (
    id bigint NOT NULL
);
CREATE TABLE public.account_credentials (
    account_id uuid NOT NULL,
    ciphertext bytea NOT NULL,
    wrapped_data_key bytea NOT NULL,
    key_version smallint NOT NULL,
    updated_at timestamp with time zone NOT NULL
);
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

COPY public.journal_entries (notes, position_id) FROM stdin;
COPY public.positions (id, symbol_norm) FROM stdin;	11111111-1111-1111-1111-111111111111
COPY public.account_credentials (account_id, key_version) FROM stdin;	22222222-2222-2222-2222-222222222222
\.

COPY public.account_credentials (account_id, ciphertext, wrapped_data_key, key_version, updated_at) FROM stdin;
33333333-3333-3333-3333-333333333333	\\x00	\\x01	26417	2026-09-07 10:00:00+00
44444444-4444-4444-4444-444444444444	\\x02	\\x03	26417	2026-09-07 10:00:00+00
\.

COPY public.reflections (position_id, free_text) FROM stdin;
11111111-1111-1111-1111-111111111111	не двигать стоп руками
\.

--
-- PostgreSQL database dump complete
--
SQL

gzip -c <"$WORK/full.sql" >"$WORK/full.sql.gz"

echo "test-scripts: backup / restore / update — то, что решает судьбу данных"
echo ""
echo "-- дамп: целый против огрызка --------------------------------------"

## ----------------------------------------------------------------------------

expect_accept "целый дамп принимается" "$WORK/full.sql.gz"

REPORT="$WORK/report.full"
td_dump_report "$WORK/full.sql.gz" >"$REPORT"

MISSED=""
for table in positions journal_entries reflections account_credentials; do
  grep -qx "CREATED $table" "$REPORT" || MISSED="$MISSED $table"
done
if [ -z "$MISSED" ]; then
  ok "все CREATE TABLE найдены"
else
  bad "в отчёте нет CREATED:$MISSED"
fi

grep -qx "COMPLETE 1" "$REPORT" && ok "отметка об окончании дампа найдена" ||
  bad "не найдена отметка об окончании дампа"

# Главное свойство разбора: строки внутри COPY — данные, а не разметка. Заметка
# пользователя, начинающаяся словами «COPY public.… FROM stdin;», обязана посчитаться
# одной строкой journal_entries, а не открыть второй блок.
same "строки внутри COPY посчитаны верно" \
  "$(awk '$1 == "TABLE" { print $2 "=" $3 }' "$REPORT" | sort | tr '\n' ' ')" \
  "account_credentials=2 journal_entries=2 positions=2 reflections=1 "

# И CREATE TABLE внутри данных не должен добавить несуществующую таблицу.
cat >"$WORK/decoy.sql" <<'SQL'
--
-- PostgreSQL database dump
--

CREATE TABLE public.journal_entries (
    notes text
);

COPY public.journal_entries (notes) FROM stdin;
CREATE TABLE public.made_up (id uuid);
\.

--
-- PostgreSQL database dump complete
--
SQL
gzip -c <"$WORK/decoy.sql" >"$WORK/decoy.sql.gz"
if td_dump_report "$WORK/decoy.sql.gz" | grep -qx "CREATED made_up"; then
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

## ----------------------------------------------------------------------------
## Наш дамп против чужого
## ----------------------------------------------------------------------------

echo ""
echo "-- дамп: наш против чужого ------------------------------------------"

same "дамп TradeDesk опознан" "$(td_dump_looks_like_tradedesk "$REPORT")" ""

cat >"$WORK/alien.sql" <<'SQL'
--
-- PostgreSQL database dump
--

CREATE TABLE public.customers (
    id integer NOT NULL
);

COPY public.customers (id) FROM stdin;
1
\.

--
-- PostgreSQL database dump complete
--
SQL
gzip -c <"$WORK/alien.sql" >"$WORK/alien.sql.gz"
td_dump_report "$WORK/alien.sql.gz" >"$WORK/report.alien"
same "чужой дамп не принят за наш" \
  "$(td_dump_looks_like_tradedesk "$WORK/report.alien")" \
  "users trading_accounts deals positions"

## ----------------------------------------------------------------------------
## Предпросмотр restore: что человек видит перед необратимой операцией
## ----------------------------------------------------------------------------

echo ""
echo "-- предпросмотр restore ---------------------------------------------"

# Слепок базы: есть таблица tags, которой в дампе нет вовсе, и есть positions, строк
# в которой сейчас больше, чем в бэкапе.
printf 'positions\t5\njournal_entries\t2\nusers\t1\ntags\t2\n' >"$WORK/counts"
td_restore_preview "$WORK/counts" "$REPORT" >"$WORK/preview"

same "строк станет меньше — помечено стрелкой" \
  "$(awk '$1 == "←" && $2 == "positions" { print $3, $4 }' "$WORK/preview")" \
  "5 2"

same "строк столько же — без стрелки" \
  "$(awk '$1 == "journal_entries" { print $2, $3 }' "$WORK/preview")" \
  "2 2"

# Ради этой строки предпросмотр и переписан: таблицы tags в дампе нет, и восстановление
# её не тронет. «станет 0» здесь было бы прямой ложью — а предпросмотр единственное,
# по чему человек решает, продолжать ли.
same "таблицы нет в дампе — сказано, что она останется" \
  "$(awk '$1 == "tags" { print $2, $3, $4, $5 }' "$WORK/preview")" \
  "2 останется как есть"

# А таблица, которая в дампе ЕСТЬ и пуста, обязана остаться со стрелкой: её строки
# действительно исчезнут. Отличие от предыдущего случая и есть весь смысл правки.
same "таблица в дампе без строк показана нулём, а не «останется»" \
  "$(awk '$1 == "←" && $2 == "users" { print $3, $4 }' "$WORK/preview")" \
  "1 0"

same "стрелок ровно две — positions и users" "$(grep -c '←' "$WORK/preview")" "2"

same "список отсутствующих в дампе таблиц" \
  "$(td_dump_absent_tables "$WORK/counts" "$REPORT" | tr '\n' ' ')" \
  "tags "

## ----------------------------------------------------------------------------
## MASTER_KEY: отпечатки внутри бэкапа и вердикт сверки
## ----------------------------------------------------------------------------

echo ""
echo "-- сверка MASTER_KEY ------------------------------------------------"

# Номер колонки key_version читается из заголовка COPY. Поддельный заголовок в тексте
# заметки (он есть в образце выше) не должен подсунуть свои значения.
same "key_version прочитан из дампа" \
  "$(td_dump_key_versions "$WORK/full.sql.gz" | tr '\n' ' ')" \
  "26417 "

same "в дампе без счетов отпечатков нет" \
  "$(td_dump_key_versions "$WORK/alien.sql.gz" | tr '\n' ' ')" \
  ""

verdict() { td_key_verdict "$@" | cut -f1; }
unknowns() { td_key_verdict "$@" | cut -f2; }

same "сверять не с чем" "$(verdict 111 '')" "none"
same "всё на текущем ключе" "$(verdict 111 '' 111)" "current"
same "всё на предыдущем ключе" "$(verdict 111 222 222)" "previous"
same "ротация на середине — оба ключа знакомы" "$(verdict 111 222 111 222)" "current"
same "чужой ключ распознан" "$(verdict 111 222 333)" "unknown"
same "чужой ключ назван" "$(unknowns 111 222 111 333 444)" "333 444"
same "без MASTER_KEY_PREVIOUS второй ключ чужой" "$(verdict 111 '' 111 222)" "unknown"

## ----------------------------------------------------------------------------
## Ротация: единственное место, которое удаляет бэкапы
## ----------------------------------------------------------------------------

echo ""
echo "-- ротация бэкапов --------------------------------------------------"

# Настоящий бэкап здесь — любой валидный gzip: ротация смотрит именно на распаковку.
make_backup() {
  gzip -c <"$WORK/full.sql" >"$1"
  touch -t "$2" "$1"
}

count_files() { find "$1" -maxdepth 1 -name 'td-*.sql.gz' | wc -l | tr -d ' '; }

# Проба ревьюера: пять настоящих копий и куча мусора с такими же именами. До правки
# ротация считала мусор бэкапами и удаляла все настоящие.
DIR="$WORK/junk"
mkdir -p "$DIR"
i=1
while [ "$i" -le 5 ]; do
  make_backup "$DIR/td-2026090$i-120000.sql.gz" "20260$((i + 1))011200"
  i=$((i + 1))
done
i=1
while [ "$i" -le 13 ]; do
  : >"$DIR/td-junk-empty-$i.sql.gz"
  i=$((i + 1))
done
i=1
while [ "$i" -le 7 ]; do
  printf 'не gzip\n' >"$DIR/td-junk-text-$i.sql.gz"
  i=$((i + 1))
done
printf 'не gzip\n' >"$DIR/td-21000101-000000.sql.gz"
touch -t 210001010000 "$DIR/td-21000101-000000.sql.gz"

td_rotate_backups "$DIR" 14 "" >"$WORK/rot.out" 2>"$WORK/rot.err"

SURVIVED=0
i=1
while [ "$i" -le 5 ]; do
  [ -f "$DIR/td-2026090$i-120000.sql.gz" ] && SURVIVED=$((SURVIVED + 1))
  i=$((i + 1))
done
same "мусор не вытеснил настоящие копии" "$SURVIVED" "5"
same "ничего не удалено — целых копий меньше четырнадцати" "$(count_files "$DIR")" "26"
if grep -q 'не распаковываются' "$WORK/rot.err"; then
  ok "про нераспаковываемые файлы сказано вслух"
else
  bad "мусор пропущен молча — человек о нём не узнает"
fi

# Ротация всё-таки удаляет — когда целых копий действительно больше нормы.
DIR2="$WORK/rotate"
mkdir -p "$DIR2"
make_backup "$DIR2/td-20260901-120000.sql.gz" "202609011200"
make_backup "$DIR2/td-20260902-120000.sql.gz" "202609021200"
make_backup "$DIR2/td-20260903-120000.sql.gz" "202609031200"
make_backup "$DIR2/td-20260904-120000.sql.gz" "202609041200"
: >"$DIR2/td-broken.sql.gz"

td_rotate_backups "$DIR2" 2 "" >"$WORK/rot2.out" 2>"$WORK/rot2.err"

same "оставлены две свежие целые копии" \
  "$(find "$DIR2" -maxdepth 1 -name 'td-2026*' | sort | tr '\n' ' ')" \
  "$DIR2/td-20260903-120000.sql.gz $DIR2/td-20260904-120000.sql.gz "
if [ -f "$DIR2/td-broken.sql.gz" ]; then
  ok "битый файл не удалён — сносить чужое скрипт не берётся"
else
  bad "битый файл удалён: ротация решила за человека"
fi

# Файл этого прогона защищён отдельно, даже если по времени он не в первых $KEEP.
DIR3="$WORK/protect"
mkdir -p "$DIR3"
make_backup "$DIR3/td-20260901-120000.sql.gz" "202609011200"
make_backup "$DIR3/td-20260902-120000.sql.gz" "202609021200"
make_backup "$DIR3/td-20260903-120000.sql.gz" "202609031200"
td_rotate_backups "$DIR3" 1 "$DIR3/td-20260901-120000.sql.gz" >/dev/null 2>&1
if [ -f "$DIR3/td-20260901-120000.sql.gz" ]; then
  ok "защищённый файл переживает ротацию"
else
  bad "ротация удалила файл, который ей передали как защищённый"
fi

## ----------------------------------------------------------------------------
## update: разбор версии, имени архива и ответа GitHub
## ----------------------------------------------------------------------------

echo ""
echo "-- update: разбор версии --------------------------------------------"

same "тег → версия" "$(td_tag_to_version v0.2.0)" "0.2.0"
same "тег с rc → версия PEP 440" "$(td_tag_to_version v1.0.0-rc1)" "1.0.0rc1"
same "тег без v" "$(td_tag_to_version 0.2.0)" "0.2.0"

same "имя архива → тег" "$(td_zip_to_tag /tmp/скачано/tradedesk-0.2.0.zip)" "v0.2.0"
same "имя архива с rc → тег" "$(td_zip_to_tag tradedesk-1.0.0-rc1.zip)" "v1.0.0-rc1"

# Ответ GitHub приходит одной строкой; tag_name идёт раньше body, где текст релиза
# содержит такую же строку — и она не должна перебить настоящий тег.
cat >"$WORK/release.json" <<'JSON'
{"url":"https://api.github.com/repos/x/y/releases/1","tag_name":"v0.3.0","name":"0.3.0","body":"починили update, раньше он брал \"tag_name\": \"v0.0.1\" из тела","draft":false}
JSON
same "tag_name из ответа GitHub" "$(td_parse_tag_name "$WORK/release.json")" "v0.3.0"

printf '{"message":"Not Found"}\n' >"$WORK/notfound.json"
same "релизов нет — тега нет" "$(td_parse_tag_name "$WORK/notfound.json")" ""

echo ""
if [ "$FAILED" = "0" ]; then
  echo "test-scripts: всё сошлось."
else
  echo "test-scripts: есть провалы." >&2
  exit 1
fi
