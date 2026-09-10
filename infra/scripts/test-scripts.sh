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
# Исключение — start.sh. Он проверяется целиком, прогоном: X-53 и X-54 про то, что человек
# читает на экране, и утверждение «сообщение правильное» без запуска ничем не подтверждается.
# Докер для этого не нужен — подставной `docker` в PATH отвечает за него (см. ниже).
#
# Что остаётся непокрытым и почему: сам перенос файлов, метка незавершённого обновления,
# сборка образов и сверка версии с ответом /api/v1/version — им нужен докер и настоящий
# релиз, они проверяются прогоном руками (см. SETUP.md, раздел «Что здесь проверено, а что
# нет»).
set -eu

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TD_ROOT="$ROOT"
. "$ROOT/infra/scripts/common.sh"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/tdscripts.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT INT TERM

FAILED=0

# printf, а не echo, и по той же причине, что в common.sh: в названиях проверок теперь
# встречаются windows-пути, и `echo` на macOS развернул бы «\b» в Git\bin в возврат
# каретки — название проверки врало бы про то, что проверка как раз и стережёт.
ok() { printf '  ok    %s\n' "$1"; }
bad() {
  printf '  ПРОВАЛ %s\n' "$1" >&2
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

## ----------------------------------------------------------------------------
## start.sh: путь установки и код возврата compose
## ----------------------------------------------------------------------------

echo ""
echo "-- start.sh: путь и код возврата ------------------------------------"

same "чистая латиница — путь годен" "$(td_path_non_ascii "/Users/ivan/tradedesk" && echo да || echo нет)" "нет"
same "пробел в пути годен" "$(td_path_non_ascii "/Users/ivan/My Files/td" && echo да || echo нет)" "нет"
same "кириллица в пути не годна" "$(td_path_non_ascii "/Users/Никита/td" && echo да || echo нет)" "да"
same "кириллица в середине не годна" "$(td_path_non_ascii "C:/Пользователи/td" && echo да || echo нет)" "да"
same "управляющий символ не годен" "$(td_path_non_ascii "$(printf '/tmp/a\tb')" && echo да || echo нет)" "да"
# Перевод строки внутри пути легален, а построчный grep его пропускал: каждая строка
# по отдельности печатна.
same "перевод строки в пути не годен" "$(td_path_non_ascii "$(printf '/tmp/a\nb')" && echo да || echo нет)" "да"

# Здесь запускается сам start.sh, а не его отдельные куски: X-53 и X-54 — про то, что
# человек видит на экране, и проверить это можно только прогоном. Docker для этого не
# нужен и не поднимается: подставной `docker` в PATH отвечает «info — да», а на compose
# падает с кодом 17. Это дешевле контейнера и воспроизводит ровно ту ветку.
STUB_BIN="$WORK/stubbin"
mkdir -p "$STUB_BIN"
cat >"$STUB_BIN/docker" <<'STUB'
#!/bin/sh
[ "$1" = "info" ] && exit 0
echo "stub docker: $*"
exit 17
STUB
chmod +x "$STUB_BIN/docker"

# Тот же подставной docker, но вместо кода возврата убивает подоболочку, в которой
# запущен, — так же, как это делает Ctrl-C по всей группе процессов. Кода возврата после
# этого нет ни у кого, и start.sh обязан сказать это словами, а не оставить дыру
# в предложении. `sleep` держит открытым конец конвейера: без него tee завершится раньше,
# чем сигнал дойдёт, и ветка не воспроизведётся.
STUB_KILL="$WORK/stubkill"
mkdir -p "$STUB_KILL"
cat >"$STUB_KILL/docker" <<'STUB'
#!/bin/sh
[ "$1" = "info" ] && exit 0
echo "stub docker: убиваю подоболочку"
kill -KILL "$PPID" 2>/dev/null
sleep 1
STUB
chmod +x "$STUB_KILL/docker"

make_installation() {
  mkdir -p "$1/infra/scripts"
  cp "$ROOT/infra/scripts/start.sh" "$ROOT/infra/scripts/update.sh" \
    "$ROOT/infra/scripts/restore.sh" "$ROOT/infra/scripts/common.sh" "$1/infra/scripts/"
  chmod +x "$1/infra/scripts/start.sh" "$1/infra/scripts/update.sh" \
    "$1/infra/scripts/restore.sh"
  : >"$1/docker-compose.yml"
  : >"$1/.env.example"
  printf 'POSTGRES_PASSWORD=stub\n' >"$1/.env"
}

run_start() {
  # $1 — подставной docker, $2 — установка, дальше — переменные окружения ИМЯ=значение.
  bin="$1"
  installation="$2"
  shift 2
  if env "$@" PATH="$bin:$PATH" sh "$installation/infra/scripts/start.sh" \
    >"$WORK/start.out" 2>&1; then
    echo 0
  else
    echo "$?"
  fi
}

run_update() {
  # update.sh при запуске переселяется во временную копию и работает оттуда; проверяется
  # он тем же способом, что start.sh, — прогоном, потому что проверяется вывод.
  if env PATH="$STUB_BIN:$PATH" sh "$1/infra/scripts/update.sh" --check \
    >"$WORK/update.out" 2>&1; then
    echo 0
  else
    echo "$?"
  fi
}

run_restore() {
  # $1 — установка, $2 — файл копии. --yes здесь безопасен: до вопроса дело не дойдёт,
  # а если дойдёт — упрётся в подставной docker, а не в базу.
  if env PATH="$STUB_BIN:$PATH" sh "$1/infra/scripts/restore.sh" "$2" --yes \
    >"$WORK/restore.out" 2>&1; then
    echo 0
  else
    echo "$?"
  fi
}

if td_path_non_ascii "$WORK"; then
  echo "  пропуск  прогон start.sh: во временном каталоге $WORK уже есть не-ASCII"
else
  INST_OK="$WORK/install-ok"
  make_installation "$INST_OK"
  same "start.sh не рапортует об успехе поверх упавшего compose" \
    "$(run_start "$STUB_BIN" "$INST_OK")" "1"
  if grep -q "завершился с кодом 17" "$WORK/start.out"; then
    ok "start.sh называет код возврата compose числом (X-53)"
  else
    bad "start.sh потерял код возврата compose:"
    sed 's/^/        /' "$WORK/start.out" >&2
  fi

  # Сборку прервали сигналом: кода возврата нет ни у кого, и это должно быть сказано
  # словами. До X-53 здесь оставался пробел в предложении, а SETUP.md учит человека
  # смотреть именно на это число.
  same "start.sh переживает убитую сборку" "$(run_start "$STUB_KILL" "$INST_OK")" "1"
  START_KILLED="$(cat "$WORK/start.out")"
  case "$START_KILLED" in
    *"код возврата неизвестен"*) ok "прерванная сборка названа словами, а не пробелом" ;;
    *) bad "прерванная сборка описана не так: $START_KILLED" ;;
  esac
  case "$START_KILLED" in
    *"завершился с кодом  "* | *"завершился с кодом —"*)
      bad "в сообщении осталась дыра на месте кода возврата"
      ;;
    *) ok "дыры на месте кода возврата нет" ;;
  esac

  INST_RU="$WORK/установка"
  make_installation "$INST_RU"
  same "start.sh отказывается стартовать из пути с кириллицей" \
    "$(run_start "$STUB_BIN" "$INST_RU")" "1"
  START_RU="$(cat "$WORK/start.out")"
  case "$START_RU" in
    *"символы, которые Docker не понимает"*) ok "отказ называет причину, а не gRPC (X-54)" ;;
    *) bad "отказ по пути не назвал причину: $START_RU" ;;
  esac
  # Путь сверяется разрешённый: start.sh печатает результат `pwd`, а под macOS TMPDIR —
  # это симлинк /var → /private/var, и дословное сравнение поймало бы симлинк, а не ошибку.
  INST_RU_REAL="$(cd "$INST_RU" && pwd)"
  case "$START_RU" in
    *"$INST_RU_REAL"*) ok "отказ показывает саму папку" ;;
    *) bad "в отказе нет пути установки" ;;
  esac
  case "$START_RU" in
    *"C:\\tradedesk"*) ok "отказ показывает пример пути без потери обратного слэша" ;;
    *) bad "пример пути искажён — echo съел обратный слэш" ;;
  esac
  case "$START_RU" in
    *"stub docker"*) bad "проверка пути пропустила compose вперёд себя" ;;
    *) ok "compose до проверки пути не зовётся" ;;
  esac

  case "$START_RU" in
    *"TD_ALLOW_NON_ASCII_PATH=1 DOCKER_BUILDKIT=0"*)
      ok "отказ называет обход целиком, обеими переменными"
      ;;
    *) bad "в отказе нет обхода — человек о нём больше нигде не узнает" ;;
  esac

  same "TD_ALLOW_NON_ASCII_PATH=1 снимает проверку" \
    "$(run_start "$STUB_BIN" "$INST_RU" TD_ALLOW_NON_ASCII_PATH=1)" "1"
  if grep -q "завершился с кодом 17" "$WORK/start.out"; then
    ok "со снятой проверкой start.sh доходит до compose"
  else
    bad "TD_ALLOW_NON_ASCII_PATH=1 не пустил дальше:"
    sed 's/^/        /' "$WORK/start.out" >&2
  fi

  # update.sh получил ту же проверку и по более дорогой причине: он переносит файлы
  # установки. Отказ обязан случиться до этого, а не после.
  same "update.sh отказывается работать из пути с кириллицей" "$(run_update "$INST_RU")" "1"
  UPDATE_RU="$(cat "$WORK/update.out")"
  case "$UPDATE_RU" in
    *"символы, которые Docker не понимает"*) ok "update.sh отказывает по той же причине" ;;
    *) bad "update.sh отказал не по пути: $UPDATE_RU" ;;
  esac

  # У restore довод сильнее, чем у update: он кончается вызовом start.sh, а между началом
  # и этим отказом лежала бы перезаписанная база.
  mkdir -p "$INST_RU/backups"
  : | gzip >"$INST_RU/backups/td-20260101-000000.sql.gz"
  same "restore.sh отказывается работать из пути с кириллицей" \
    "$(run_restore "$INST_RU" "$INST_RU/backups/td-20260101-000000.sql.gz")" "1"
  RESTORE_RU="$(cat "$WORK/restore.out")"
  case "$RESTORE_RU" in
    *"символы, которые Docker не понимает"*) ok "restore.sh отказывает по той же причине" ;;
    *) bad "restore.sh отказал не по пути: $RESTORE_RU" ;;
  esac
  case "$RESTORE_RU" in
    *"stub docker"*) bad "restore.sh дошёл до docker раньше проверки пути" ;;
    *) ok "restore.sh не трогает базу до проверки пути" ;;
  esac
fi

## ----------------------------------------------------------------------------
## Пауза в `.bat`. Запустить их на macOS нечем, поэтому проверяются байты — тем же
## способом и по той же причине, что файлы установки коллектора
## (apps/collector-mt5/tests/test_install_files.py).
##
## Окно, открытое двойным щелчком, закрывается вместе с последней строкой вывода. Для
## start.bat это адреса приложения, для остальных — путь к свежей копии, таблица «что
## будет перезаписано», предупреждение про MASTER_KEY. Без паузы у главного шага установки
## нет видимого результата (X-61). Проверяются все `.bat` разом, а не список поимённо:
## файл, добавленный позже и забывший паузу, обязан провалить гейт сам.
## ----------------------------------------------------------------------------

for bat_file in "$ROOT"/infra/scripts/*.bat; do
  bat_name="$(basename "$bat_file")"
  # find-bash.bat человек не запускает: его зовут через `call` остальные, и пауза в нём
  # повесила бы каждый из них. Свои проверки у него ниже, в разделе про поиск bash.
  if [ "$bat_name" = "find-bash.bat" ]; then
    continue
  fi
  if grep -qF 'if not "%TD_NO_PAUSE%"=="1" pause' "$bat_file"; then
    ok "$bat_name ждёт клавиши перед закрытием окна"
  else
    bad "$bat_name закроет окно вместе с выводом — нет паузы с TD_NO_PAUSE"
  fi
  # Код возврата сохраняется в RC до паузы: между вызовом bash и exit стоит интерактивная
  # команда, и полагаться на %errorlevel% после неё мы не будем — проверить это нечем.
  if grep -qF 'exit /b %RC%' "$bat_file"; then
    ok "$bat_name отдаёт сохранённый код возврата, а не то, что осталось после паузы"
  else
    bad "$bat_name не заканчивается exit /b %RC% — код скрипта наружу не уйдёт"
  fi
done

# Обратная сторона: паузу нельзя занести в `.sh`. Их зовут make up/make down и сам
# update.sh, и ожидание клавиши там повесило бы и гейт, и обновление.
#
# common.sh в список не входит, и это проверено, а не забыто: в нём живёт `td_confirm` со
# своим `read` — тот самый, которым `restore.sh` требует набрать слово перед тем, как
# затереть базу. Запрет `read` в common.sh сломал бы единственное место, где ждать ввода
# и надо. Опасен `read` на пути, который исполняют start.sh и stop.sh, а не в функции,
# которую они не зовут, — поэтому сторож смотрит именно на них.
for sh_file in start.sh stop.sh; do
  if grep -qE '(^|[^_[:alnum:]])read([[:space:]]|$)' "$ROOT/infra/scripts/$sh_file"; then
    bad "$sh_file ждёт ввода — make up/make down повиснут"
  else
    ok "$sh_file ввода не ждёт"
  fi
done

## ----------------------------------------------------------------------------
## Как `.bat` находят bash (X-63). Прогнать их на macOS нечем — проверяются байты.
##
## На живой Windows 10 22H2 (19045.6332) `where bash` поломался дважды подряд: сразу
## после установки Git он молчал (установщик кладёт в PATH только Git\cmd, а bash.exe
## лежит в Git\bin), а после установки WSL2 стал находить C:\Windows\System32\bash.exe —
## запускалку подсистемы Linux. Запуск через неё падает с «execvpe(/bin/bash) failed».
## Правкой пользовательского PATH второе не лечится: системный PATH просматривается
## раньше. Отсюда сторожа ниже: `where bash` не должно остаться нигде, кроме комментария.
## ----------------------------------------------------------------------------

echo ""
echo "-- .bat: поиск bash (X-63) -----------------------------------------"

FINDER="$ROOT/infra/scripts/find-bash.bat"
if [ -f "$FINDER" ]; then
  ok "find-bash.bat на месте"
else
  bad "find-bash.bat пропал — все шесть обёрток остались без bash"
fi

# rem-строки не считаются: в самом find-bash.bat `where bash` назван — там объяснено,
# почему им нельзя пользоваться. Ищется исполняемая строка.
bat_code() { grep -viE '^[[:space:]]*rem([[:space:]]|$)' "$1"; }

for bat_file in "$ROOT"/infra/scripts/*.bat; do
  bat_name="$(basename "$bat_file")"
  if bat_code "$bat_file" | grep -qiF 'where bash'; then
    bad "$bat_name спрашивает bash у PATH — после установки WSL там System32\\bash.exe"
  else
    ok "$bat_name не спрашивает bash у PATH"
  fi
  if [ "$bat_name" = "find-bash.bat" ]; then
    continue
  fi
  if grep -qF 'call "%~dp0find-bash.bat"' "$bat_file"; then
    ok "$bat_name ищет bash через общий find-bash.bat"
  else
    bad "$bat_name не зовёт find-bash.bat — своя копия поиска разойдётся молча"
  fi
  # Полный путь, а не голое `bash`: даже найденный по путям bash нельзя звать по имени —
  # разрешать имя снова будет PATH, и System32 опять окажется первым.
  if grep -qF '"%TD_BASH%" "%~dp0' "$bat_file"; then
    ok "$bat_name зовёт bash по полному пути"
  else
    bad "$bat_name зовёт bash не по полному пути из TD_BASH"
  fi
done

# setlocal в find-bash.bat стёр бы TD_BASH на выходе, и вызывающий получил бы пустоту.
if bat_code "$FINDER" | grep -qiE '^[[:space:]]*setlocal'; then
  bad "find-bash.bat делает setlocal — TD_BASH не доживёт до вызывающего"
else
  ok "find-bash.bat не делает setlocal — TD_BASH доходит до вызывающего"
fi

# Те самые три места из измерения плюс вывод из git.exe для установки в чужую папку.
for probe in \
  '%ProgramFiles%\Git\bin\bash.exe' \
  '%ProgramFiles(x86)%\Git\bin\bash.exe' \
  '%LOCALAPPDATA%\Programs\Git\bin\bash.exe'; do
  if grep -qF "if exist \"$probe\"" "$FINDER"; then
    ok "find-bash.bat проверяет $probe"
  else
    bad "find-bash.bat не проверяет $probe"
  fi
done
if grep -qF '%%~$PATH:I' "$FINDER"; then
  ok "find-bash.bat выводит путь из git.exe — Git в нестандартной папке тоже находится"
else
  bad "find-bash.bat не пробует вывести bash из git.exe"
fi

# Отказ обязан называть, где искали: «поставь Git» — неверный совет тому, у кого Git стоит.
if grep -qF 'Искали здесь:' "$FINDER"; then
  ok "отказ называет, где искали"
else
  bad "отказ не называет мест поиска — человек с установленным Git прочтёт «поставь Git»"
fi
# Именно в напечатанном тексте, а не где-нибудь в файле: TD_BASH там встречается и в самом
# поиске, и этого хватило бы, чтобы сторож промолчал о выкинутой подсказке.
if grep -iE '^[[:space:]]*echo([[:space:]]|$)' "$FINDER" | grep -qF 'TD_BASH'; then
  ok "отказ называет способ задать путь вручную"
else
  bad "отказ не оставляет выхода для Git в нестандартной папке"
fi

## ----------------------------------------------------------------------------
## Вывод скриптов называет команды той платформы, где человек стоит (X-64).
##
## `make` на Windows не ставится и по SETUP.md §1 не нужен, а `.bat` бессмысленны на
## macOS. Человек читает вывод В МОМЕНТ действия, и совет выполнить несуществующую
## команду здесь дороже той же неточности в документе. Найдено на живой машине:
## «Дальше: make up» в окне init.bat.
## ----------------------------------------------------------------------------

echo ""
echo "-- вывод скриптов: команды по платформе (X-64) ----------------------"

# Обе ветки на одной машине: td_is_windows смотрит на `uname -s`, и подставной uname
# в PATH отвечает за Git Bash. Своего seam-переключателя в common.sh для этого нет
# намеренно — переменная, меняющая тексты, однажды окажется выставленной случайно.
STUB_WIN="$WORK/stubwin"
mkdir -p "$STUB_WIN"
cat >"$STUB_WIN/uname" <<'STUB'
#!/bin/sh
[ "$1" = "-s" ] && { echo "MINGW64_NT-10.0-19045"; exit 0; }
exec /usr/bin/uname "$@"
STUB
chmod +x "$STUB_WIN/uname"

as_windows() {
  # $1 — что позвать. OS=Windows_NT добавлен не для проверки, а чтобы подделка была
  # похожа на настоящий Git Bash целиком.
  PATH="$STUB_WIN:$PATH" OS="Windows_NT" sh -c ". \"$ROOT/infra/scripts/common.sh\"; $1"
}

same "на macOS действие называется make up" "$(td_cmd up)" "make up"
same "на macOS остановка называется make down" "$(td_cmd down)" "make down"
same "на macOS восстановление называется с файлом" "$(td_cmd restore)" "make restore file=…"
same "на macOS путь скрипта — .sh" "$(td_script backup)" "infra/scripts/backup.sh"

same "на Windows действие называется start.bat" \
  "$(as_windows 'td_cmd up')" 'infra\scripts\start.bat'
same "на Windows создание .env называется init.bat" \
  "$(as_windows 'td_cmd init')" 'infra\scripts\init.bat'
same "на Windows остановка называется stop.bat" \
  "$(as_windows 'td_cmd down')" 'infra\scripts\stop.bat'
same "на Windows восстановление называется restore.bat" \
  "$(as_windows 'td_cmd restore')" 'infra\scripts\restore.bat'
same "на Windows путь скрипта — .bat" \
  "$(as_windows 'td_script backup')" 'infra\scripts\backup.bat'
# Обратный слэш обязан дожить до экрана: `echo` на macOS и на Debian разворачивает
# escape-последовательности, и `\r` в «infra\scripts\restore.bat» съел бы полстроки.
# Проверено: та же строка через echo печатается как «infra\scriptsestore.bat».
same "обратные слэши не съедаются печатью" \
  "$(as_windows 'td_say "$(td_script restore)"')" 'infra\scripts\restore.bat'

# Ни один скрипт установки не имеет права называть команду в открытую: имя выбирает
# td_cmd, и только он. common.sh исключён — он и есть то единственное место.
# Скрипты разработчика (make-release, ci-target, тесты) сюда не входят: их читает не
# тестировщик, а человек с make.
for sh_file in init-env.sh start.sh stop.sh backup.sh restore.sh update.sh; do
  if grep -vE '^[[:space:]]*#' "$ROOT/infra/scripts/$sh_file" | grep -qE '(^|[^-])make '; then
    bad "$sh_file называет make — на Windows этой команды нет"
  else
    ok "$sh_file не называет make"
  fi
done

# ADR-0005: установка обновляется распаковкой релиза, а не git. Совет `git pull` тут
# неверен и человеку, у которого Git есть только ради bash.
for sh_file in init-env.sh start.sh stop.sh backup.sh restore.sh update.sh common.sh; do
  if grep -vE '^[[:space:]]*#' "$ROOT/infra/scripts/$sh_file" | grep -qF 'git pull'; then
    bad "$sh_file советует git pull — дистрибуция архивом (ADR-0005)"
  else
    ok "$sh_file не советует git pull"
  fi
done

# Опечатка в ключе td_cmd молча напечатала бы сам ключ: «Дальше: sart». Ключи известны,
# поэтому проверяются они, а не поведение на неизвестном ключе.
KNOWN_CMD=" init up down backup restore update "
KNOWN_SCRIPT=" start stop backup restore update "
for sh_file in init-env.sh start.sh stop.sh backup.sh restore.sh update.sh; do
  for key in $(grep -o 'td_cmd [a-z-]*' "$ROOT/infra/scripts/$sh_file" | cut -d' ' -f2); do
    case "$KNOWN_CMD" in
      *" $key "*) ok "$sh_file: td_cmd $key — ключ известен" ;;
      *) bad "$sh_file: td_cmd $key — такого ключа нет, напечатается сам ключ" ;;
    esac
  done
  for key in $(grep -o 'td_script [a-z-]*' "$ROOT/infra/scripts/$sh_file" | cut -d' ' -f2); do
    case "$KNOWN_SCRIPT" in
      *" $key "*) ok "$sh_file: td_script $key — пара .sh/.bat сходится" ;;
      *) bad "$sh_file: td_script $key — у этого имени нет парного .bat" ;;
    esac
  done
done

echo ""
if [ "$FAILED" = "0" ]; then
  echo "test-scripts: всё сошлось."
else
  echo "test-scripts: есть провалы." >&2
  exit 1
fi
