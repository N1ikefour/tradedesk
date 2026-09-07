#!/usr/bin/env sh
# `update.bat|sh` — обновление установки до свежего релиза (SPEC.md 11.3, ADR-0005).
#
# Порядок: сверка MASTER_KEY → backup → скачивание и распаковка релиза поверх установки
# (с сохранением .env и backups/) → build → up → вывод версии. Миграции катит контейнер
# api при старте, отдельного шага нет.
#
# ⚠️ Сверка MASTER_KEY стоит ПЕРВОЙ, до бэкапа и до скачивания. Распаковка новой версии
# в отдельную папку заставляет `make init` создать НОВЫЙ ключ. База при этом остаётся
# старой, приложение поднимается, журнал на месте — а пароли брокерских счетов
# становятся нечитаемы, и коллектор молча перестаёт заходить в терминал. Симптом
# появляется через сутки и выглядит как проблема у брокера. Сверять есть с чем:
# `key_version` рядом с каждым зашифрованным блобом — отпечаток ключа (ADR-0003).
#
# ⚠️ Перенос файлов идёт через rename (`mv`), а не копированием поверх. `cp` поверх
# работающего скрипта обрезает файл, который shell ещё дочитывает, — обновление
# ломается ровно на себе самом. Плюс сам скрипт перед переносом уходит выполняться
# из временной копии: на Windows переименовать поверх открытого файла нельзя вовсе.
set -eu

## ----------------------------------------------------------------------------
## Отселение: дальше скрипт работает из временной копии, а не из установки
## ----------------------------------------------------------------------------

if [ "${TD_UPDATE_DETACHED:-}" = "1" ]; then
  TD_ROOT="$TD_UPDATE_ROOT"
  LIBDIR="$(cd "$(dirname "$0")" && pwd)"
  trap 'rm -rf "$LIBDIR"' EXIT
else
  TD_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
  SELFDIR="$(mktemp -d "${TMPDIR:-/tmp}/td-update.XXXXXX")"
  cp "$TD_ROOT/infra/scripts/update.sh" "$TD_ROOT/infra/scripts/common.sh" "$SELFDIR/"
  TD_UPDATE_DETACHED=1 TD_UPDATE_ROOT="$TD_ROOT"
  export TD_UPDATE_DETACHED TD_UPDATE_ROOT
  exec sh "$SELFDIR/update.sh" "$@"
fi

cd "$TD_ROOT"
. "$LIBDIR/common.sh"

# Откуда берётся релиз. Переопределяется только для проверки самих скриптов — человеку
# менять эти три переменные незачем.
REPO="${TD_RELEASE_REPO:-N1ikefour/tradedesk}"
API_BASE="${TD_RELEASE_API:-https://api.github.com}"
DL_BASE="${TD_RELEASE_DOWNLOAD:-https://github.com}"

STAGE_ROOT="$TD_ROOT/.td-update"
STAGE="$STAGE_ROOT/staging"
MARKER="$STAGE_ROOT/IN-PROGRESS"

usage() {
  echo "Использование: infra/scripts/update.sh [--check] [--version vX.Y.Z] [--file <zip>] [--yes]" >&2
  echo "" >&2
  echo "  без аргументов   обновиться до последнего релиза" >&2
  echo "  --check          только проверить: версия, MASTER_KEY. Ничего не менять" >&2
  echo "  --version vX.Y.Z поставить конкретную версию" >&2
  echo "  --file <zip>     взять архив с диска вместо скачивания (нет интернета —" >&2
  echo "                   скачайте zip вручную со страницы релизов и укажите его)" >&2
  echo "  --yes            не спрашивать подтверждения" >&2
}

CHECK_ONLY=0
WANT_TAG=""
LOCAL_ZIP=""
while [ $# -gt 0 ]; do
  case "$1" in
    --check) CHECK_ONLY=1 ;;
    --yes) TD_ASSUME_YES=1 ;;
    --version)
      shift
      WANT_TAG="${1:-}"
      [ -n "$WANT_TAG" ] || td_die "--version без значения."
      ;;
    --file)
      shift
      LOCAL_ZIP="${1:-}"
      [ -n "$LOCAL_ZIP" ] || td_die "--file без значения."
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "update: неизвестный аргумент '$1'" >&2
      usage
      exit 2
      ;;
  esac
  shift
done

## ----------------------------------------------------------------------------
## Инструменты и мелкие помощники
## ----------------------------------------------------------------------------

td_fetch() {
  # $1 — URL, $2 — куда положить. Ни токена, ни заголовка Authorization: репозиторий
  # открытый, и скачивание релиза не должно требовать аккаунта GitHub.
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL --retry 2 --retry-delay 2 -o "$2" "$1"
  elif command -v wget >/dev/null 2>&1; then
    wget -q -O "$2" "$1"
  else
    td_die "Нечем скачивать — нужен curl или wget.
На Windows curl приезжает вместе с Git for Windows."
  fi
}

# Распаковка zip. Каждый вариант проверяется на месте, потому что набор инструментов
# отличается: на macOS есть unzip, в Git Bash его НЕТ, а bsdtar (`tar.exe`) есть
# в самой Windows 10+. PowerShell — последний рубеж.
td_unzip() {
  archive="$1"
  dest="$2"
  mkdir -p "$dest"
  if command -v unzip >/dev/null 2>&1; then
    unzip -q "$archive" -d "$dest"
    return
  fi
  if command -v bsdtar >/dev/null 2>&1; then
    bsdtar -x -f "$archive" -C "$dest"
    return
  fi
  if command -v tar >/dev/null 2>&1 && tar -tf "$archive" >/dev/null 2>&1; then
    tar -x -f "$archive" -C "$dest"
    return
  fi
  if command -v powershell >/dev/null 2>&1; then
    win_archive="$archive"
    win_dest="$dest"
    if command -v cygpath >/dev/null 2>&1; then
      win_archive="$(cygpath -w "$archive")"
      win_dest="$(cygpath -w "$dest")"
    fi
    powershell -NoProfile -NonInteractive -Command \
      "Expand-Archive -LiteralPath '$win_archive' -DestinationPath '$win_dest' -Force"
    return
  fi
  td_die "Нечем распаковать zip: нет ни unzip, ни bsdtar, ни powershell.
Распакуйте архив вручную и обновитесь из распакованного."
}

# Версия пакета из тега: 'v' не входит, '-rc1' пишется как 'rc1' (PEP 440).
# Ровно то же преобразование делает infra/scripts/make-release.sh.
tag_to_version() {
  printf '%s' "${1#v}" | sed 's/-rc/rc/'
}

## ----------------------------------------------------------------------------
## Предусловия
## ----------------------------------------------------------------------------

td_require_installation
td_require_env
td_require_docker

# VERSION кладёт в архив make-release.sh. Его отсутствие означает, что это не установка
# из релиза, а рабочая копия репозитория, — и тогда обновляться надо через git, а не
# распаковкой архива поверх исходников.
if [ ! -f "$TD_ROOT/VERSION" ]; then
  td_die "В $TD_ROOT нет файла VERSION.

Так выглядит клон репозитория, а не установка из релизного архива. update
распаковывает zip поверх папки и в клоне затёр бы вашу рабочую копию.
Обновляйтесь через git: git pull, затем make up."
fi
CURRENT="$(tr -d ' \t\r\n' <"$TD_ROOT/VERSION")"

## ----------------------------------------------------------------------------
## Прерванное прошлое обновление
## ----------------------------------------------------------------------------

RESUME=0
if [ -f "$MARKER" ]; then
  td_say ""
  td_say "==============================================================="
  td_say " ПРЕДЫДУЩЕЕ ОБНОВЛЕНИЕ НЕ ЗАВЕРШИЛОСЬ"
  td_say "==============================================================="
  td_say ""
  sed 's/^/  /' "$MARKER"
  td_say ""
  if [ -d "$STAGE" ] && [ -n "$(find "$STAGE" -type f -print -quit 2>/dev/null)" ]; then
    td_say "  Часть файлов уже перенесена, часть осталась в $STAGE."
    td_say "  Установка сейчас наполовину новая — так её оставлять нельзя."
    td_say ""
    td_confirm "continue" "Продолжить перенос с того места, где оборвалось?"
    RESUME=1
    # Бэкап снят прерванным прогоном — его путь записан в метке. Итоговое сообщение
    # обязано на него указать: это единственный способ откатиться, если новая версия
    # не заработает.
    RESUMED_BACKUP="$(sed -n 's/^бэкап базы:[[:space:]]*//p' "$MARKER" | head -1)"
  else
    td_die "Переносить нечего: $STAGE пуст или удалён, а метка о незавершённом
переносе осталась. Установка в промежуточном состоянии.

Что делать:
  1. Запустите update заново — он скачает релиз целиком и перенесёт файлы ещё раз.
     Это безопасно: перенос идёт поверх и повторяется без последствий.
  2. Если приложение после этого не поднимется — восстановите базу из бэкапа,
     указанного выше: infra/scripts/restore.sh <файл>

Метка убирается сама, когда перенос дойдёт до конца."
  fi
elif [ -d "$STAGE_ROOT" ]; then
  # Метки нет — значит, до переноса файлов дело не дошло и установка не тронута.
  td_say "Убираю хвост прошлой попытки ($STAGE_ROOT) — файлы установки она не трогала."
  rm -rf "$STAGE_ROOT"
fi

## ----------------------------------------------------------------------------
## Сверка MASTER_KEY (ADR-0005) — раньше всего остального
## ----------------------------------------------------------------------------

PY_FINGERPRINT='
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

check_master_key() {
  td_ensure_postgres

  if ! td_table_exists account_credentials; then
    td_say "  MASTER_KEY: сверять не с чем — таблицы account_credentials в базе нет."
    td_say "             База ещё не мигрировала, зашифрованных данных не существует."
    return 0
  fi

  rows="$(td_psql "select count(*) from account_credentials" | tr -d '\r ')"
  if [ "$rows" = "0" ]; then
    # Развилка, решённая осознанно: счетов ещё нет — пропускаем сверку и продолжаем.
    # Отказ означал бы, что обновиться нельзя до первого заведённого счёта. И терять
    # здесь нечего по построению: ни одного блоба, зашифрованного старым ключом, в базе
    # нет, поэтому даже чужой ключ ничего не сделает нечитаемым.
    td_say "  MASTER_KEY: сверять не с чем — ни одного счёта с паролем ещё не заведено."
    td_say "             Обновление продолжается: нечитаемым становиться нечему."
    return 0
  fi

  # Отпечаток считает сам образ api — тем же кодом, что шифрует данные (app.core.security).
  # Ключ при этом приезжает в контейнер через env_file и в shell не попадает вовсе:
  # ни в переменную, ни в список процессов, ни в вывод.
  fp_err="$(mktemp "${TMPDIR:-/tmp}/td-fp.XXXXXX")"
  if ! fingerprints="$(td_compose run --rm --no-deps -T --entrypoint python api \
    -c "$PY_FINGERPRINT" 2>"$fp_err")"; then
    sed 's/^/      /' "$fp_err" >&2
    rm -f "$fp_err"
    td_die "Не удалось вычислить отпечаток MASTER_KEY. Обновление остановлено:
без этой сверки оно может сделать пароли счетов нечитаемыми (ADR-0005)."
  fi
  rm -f "$fp_err"

  fp_current="$(printf '%s\n' "$fingerprints" | awk '$1 == "cur" { print $2 }' | tr -d '\r')"
  fp_previous="$(printf '%s\n' "$fingerprints" | awk '$1 == "prev" { print $2 }' | tr -d '\r')"
  [ -n "$fp_current" ] || td_die "Отпечаток MASTER_KEY не вычислился."

  in_db="$(td_psql "select distinct key_version from account_credentials order by 1" |
    tr -d '\r')"

  unknown=""
  matched_current=0
  for version in $in_db; do
    if [ "$version" = "$fp_current" ]; then
      matched_current=1
    elif [ -n "$fp_previous" ] && [ "$version" = "$fp_previous" ]; then
      :
    else
      unknown="$unknown $version"
    fi
  done

  if [ -n "$unknown" ]; then
    td_die "==============================================================
 ОБНОВЛЕНИЕ ОСТАНОВЛЕНО: MASTER_KEY НЕ ТОТ
==============================================================

Пароли брокерских счетов в базе зашифрованы ДРУГИМ ключом.

  счетов с паролем в базе   $rows
  отпечаток ключа из .env   $fp_current
  отпечатки в базе          $(printf '%s' "$in_db" | tr '\n' ' ')

Скорее всего вы распаковали новую версию в отдельную папку и запустили
её там: в новой папке нет .env, make init создал новый MASTER_KEY, а база
осталась прежней. Приложение бы поднялось, журнал был бы на месте — а
коллектор перестал бы заходить в терминал, и выяснилось бы это через сутки.

Что делать:
  1. Найдите папку СТАРОЙ установки — ту, из которой приложение работало.
  2. Запустите обновление оттуда: там лежит правильный .env.
  3. Если старый .env потерян — пароли счетов не вернуть ничем, включая
     бэкап базы. Их придётся ввести заново в настройках счетов.

Ничего не изменено: ни файлы, ни база." 4
  fi

  if [ "$matched_current" = "0" ]; then
    td_say "  MASTER_KEY: ⚠️  все строки ($rows) ещё на ПРЕДЫДУЩЕМ ключе — ротация не закончена."
    td_say "             Дочитайте docs/adr/0003 и допрогоните ротацию после обновления."
  elif [ -n "$fp_previous" ]; then
    td_say "  MASTER_KEY: совпал. В .env задан и MASTER_KEY_PREVIOUS — значит, ротация"
    td_say "             ещё не убрана из окружения; после «осталось: 0» его пора стереть."
  else
    td_say "  MASTER_KEY: совпал с тем, которым зашифрованы данные. Счетов с паролем: $rows."
  fi
}

if [ "$RESUME" = "0" ]; then
  td_say ""
  td_say "Установка   $TD_ROOT"
  td_say "Версия      $CURRENT"
  td_say ""
  check_master_key
fi

## ----------------------------------------------------------------------------
## Какая версия нас ждёт
## ----------------------------------------------------------------------------

resolve_latest_tag() {
  body="$(mktemp "${TMPDIR:-/tmp}/td-rel.XXXXXX")"
  if ! td_fetch "$API_BASE/repos/$REPO/releases/latest" "$body" 2>/dev/null; then
    rm -f "$body"
    td_die "Не удалось спросить у GitHub последний релиз $REPO.
Либо нет интернета, либо релизов ещё не публиковали.
Проверьте страницу https://github.com/$REPO/releases —
если архив там есть, скачайте его и обновитесь так:
    infra/scripts/update.sh --file <путь к zip>"
  fi
  # Разбор без jq и без python: на машине пользователя нет ни того, ни другого.
  # `head -1` достаточно, потому что в ответе GitHub `tag_name` идёт раньше `body`,
  # где текст релиза мог бы содержать такую же строку. Ошибиться тегом всё равно
  # не страшно: версию внутри архива скрипт сверяет отдельно, уже после распаковки.
  tag="$(tr ',' '\n' <"$body" | sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' |
    head -1)"
  rm -f "$body"
  printf '%s' "$tag"
}

if [ "$RESUME" = "0" ]; then
  if [ -n "$LOCAL_ZIP" ] && [ -z "$WANT_TAG" ]; then
    # Версию берём из имени файла: tradedesk-0.2.0.zip. Проверяем её потом по VERSION
    # внутри архива, поэтому ошибка в имени не проходит дальше.
    WANT_TAG="v$(basename "$LOCAL_ZIP" .zip | sed 's/^tradedesk-//')"
  fi
  if [ -z "$WANT_TAG" ]; then
    td_say ""
    td_say "Спрашиваю у GitHub последний релиз $REPO…"
    WANT_TAG="$(resolve_latest_tag)"
    [ -n "$WANT_TAG" ] || td_die "GitHub не вернул tag_name — обновляться не до чего."
  fi
  TARGET="$(tag_to_version "$WANT_TAG")"

  td_say ""
  td_say "  установлено   $CURRENT"
  td_say "  доступно      $TARGET   ($WANT_TAG)"

  if [ "$TARGET" = "$CURRENT" ] && [ -z "$LOCAL_ZIP" ]; then
    td_say ""
    td_say "Уже последняя версия — обновлять нечего."
    exit 0
  fi
fi

if [ "$CHECK_ONLY" = "1" ]; then
  td_say ""
  td_say "--check: ничего не менялось."
  exit 0
fi

## ----------------------------------------------------------------------------
## Бэкап до всего остального
## ----------------------------------------------------------------------------

BACKUP_FILE="${RESUMED_BACKUP:-(не снимался — продолжение прерванного переноса)}"
if [ "$RESUME" = "0" ]; then
  td_say ""
  td_confirm "update" "Обновить установку с $CURRENT до $TARGET?"

  td_say ""
  td_say "--- Бэкап перед обновлением ------------------------------------"
  BACKUP_OUT="$(mktemp "${TMPDIR:-/tmp}/td-bkp.XXXXXX")"
  TD_BACKUP_PATH_OUT="$BACKUP_OUT" "$TD_ROOT/infra/scripts/backup.sh" ||
    td_die "Бэкап не снялся — обновление отменено. Ничего не изменено."
  BACKUP_FILE="$(cat "$BACKUP_OUT")"
  rm -f "$BACKUP_OUT"
  td_say "----------------------------------------------------------------"
fi

## ----------------------------------------------------------------------------
## Скачать, проверить, распаковать — всё это НЕ трогая установку
## ----------------------------------------------------------------------------

if [ "$RESUME" = "0" ]; then
  mkdir -p "$STAGE_ROOT"
  DOWNLOAD="$STAGE_ROOT/download"
  mkdir -p "$DOWNLOAD"
  ZIP_NAME="tradedesk-$TARGET.zip"
  ZIP="$DOWNLOAD/$ZIP_NAME"

  if [ -n "$LOCAL_ZIP" ]; then
    [ -f "$LOCAL_ZIP" ] || td_die "Файл не найден: $LOCAL_ZIP"
    cp "$LOCAL_ZIP" "$ZIP"
    if [ -f "$LOCAL_ZIP.sha256" ]; then
      cp "$LOCAL_ZIP.sha256" "$ZIP.sha256"
    fi
    td_say ""
    td_say "Архив взят с диска: $LOCAL_ZIP"
  else
    td_say ""
    td_say "Скачиваю $ZIP_NAME…"
    td_fetch "$DL_BASE/$REPO/releases/download/$WANT_TAG/$ZIP_NAME" "$ZIP" ||
      td_die "Не скачался $ZIP_NAME из релиза $WANT_TAG. Установка не тронута."
    # Контрольная сумма нужна не от злоумышленника, а от оборванной загрузки: иначе она
    # проявится непонятной ошибкой на сборке образа (docs/RELEASE.md).
    td_fetch "$DL_BASE/$REPO/releases/download/$WANT_TAG/$ZIP_NAME.sha256" "$ZIP.sha256" ||
      td_die "Не скачалась контрольная сумма $ZIP_NAME.sha256.
Проверить целостность архива нечем — обновление остановлено."
  fi

  if [ -f "$ZIP.sha256" ]; then
    EXPECTED="$(cut -d' ' -f1 <"$ZIP.sha256" | tr -d '\r\n')"
    ACTUAL="$(td_sha256 "$ZIP")"
    if [ "$EXPECTED" != "$ACTUAL" ]; then
      td_die "Контрольная сумма архива не сошлась.

  ожидалась  $EXPECTED
  получилась $ACTUAL

Загрузка оборвалась или файл подменён. Установка не тронута."
    fi
    td_say "  контрольная сумма сошлась"
  else
    td_say "  ⚠️  файла .sha256 рядом нет — целостность архива не проверена"
  fi

  td_say "Распаковываю…"
  UNPACKED="$STAGE_ROOT/unpacked"
  rm -rf "$UNPACKED"
  td_unzip "$ZIP" "$UNPACKED"

  # Внутри архива ровно один каталог tradedesk-<версия> (docs/RELEASE.md). Его надо снять,
  # иначе поверх установки легла бы вложенная копия.
  INNER="$UNPACKED/tradedesk-$TARGET"
  [ -d "$INNER" ] || td_die "В архиве нет каталога tradedesk-$TARGET.
Содержимое: $(ls "$UNPACKED" 2>/dev/null | tr '\n' ' ')
Установка не тронута."

  # Что должно приехать. Если чего-то нет — архив битый, и переносить его нельзя.
  for required in VERSION docker-compose.yml Makefile .env.example \
    infra/scripts/start.sh infra/scripts/common.sh apps/api/Dockerfile; do
    [ -e "$INNER/$required" ] ||
      td_die "В архиве нет $required — это не полный релиз. Установка не тронута."
  done

  IN_ZIP="$(tr -d ' \t\r\n' <"$INNER/VERSION")"
  [ "$IN_ZIP" = "$TARGET" ] ||
    td_die "Версия внутри архива ($IN_ZIP) не равна ожидаемой ($TARGET).
Установка не тронута."

  # .env в архиве быть не может (docs/RELEASE.md), но проверить дешевле, чем потом
  # объяснять, куда делся MASTER_KEY: перенос затёр бы его вместе с паролями счетов.
  STRAY="$(find "$INNER" -name '.env' -o -name '*.env' -o -name '.env.*' |
    grep -v '\.example$' || true)"
  [ -z "$STRAY" ] ||
    td_die "В архиве лежит файл окружения:
$STRAY
Перенос затёр бы ваш .env вместе с MASTER_KEY. Обновление остановлено."

  rm -rf "$STAGE"
  mv "$INNER" "$STAGE"
  rm -rf "$UNPACKED" "$DOWNLOAD"
fi

## ----------------------------------------------------------------------------
## Перенос поверх установки — единственный необратимый шаг
## ----------------------------------------------------------------------------

if [ "$RESUME" = "0" ]; then
  {
    echo "начато:        $(date '+%Y-%m-%d %H:%M:%S')"
    echo "было:          $CURRENT"
    echo "ставится:      $TARGET"
    echo "бэкап базы:    $BACKUP_FILE"
    echo "файлы отсюда:  $STAGE"
  } >"$MARKER"
fi

td_say ""
td_say "Переношу файлы в установку…"

# Сначала каталоги, потом файлы. Перенос — rename: он атомарен на файл и не трогает
# inode, который shell уже держит открытым. Файлы, которых в новой версии нет,
# остаются на месте — так и задумано (docs/RELEASE.md).
DIRS="$(mktemp "${TMPDIR:-/tmp}/td-dirs.XXXXXX")"
FILES="$(mktemp "${TMPDIR:-/tmp}/td-files.XXXXXX")"
trap 'rm -rf "$LIBDIR" "$DIRS" "$FILES"' EXIT

(cd "$STAGE" && find . -mindepth 1 -type d) >"$DIRS"
(cd "$STAGE" && find . -mindepth 1 -type f) >"$FILES"

MOVED=0
while IFS= read -r rel <&3; do
  [ -n "$rel" ] || continue
  mkdir -p "$TD_ROOT/${rel#./}"
done 3<"$DIRS"

while IFS= read -r rel <&3; do
  [ -n "$rel" ] || continue
  target="$TD_ROOT/${rel#./}"
  mkdir -p "$(dirname "$target")"
  mv -f "$STAGE/${rel#./}" "$target" ||
    td_die "Не удалось перенести ${rel#./}.
Установка сейчас наполовину обновлена. Метка $MARKER на месте:
запустите update ещё раз, он продолжит перенос."
  MOVED=$((MOVED + 1))
done 3<"$FILES"

# .env и backups/ в архиве отсутствуют, поэтому перенос их не задевает. Проверяем это
# фактом, а не рассуждением: цена ошибки — потерянный MASTER_KEY.
[ -f "$TD_ROOT/.env" ] ||
  td_die "После переноса пропал .env — этого не должно было случиться.
Не запускайте make init: он создаст НОВЫЙ MASTER_KEY и пароли счетов станут
нечитаемы. Верните .env из своей копии."

rm -f "$MARKER"
rm -rf "$STAGE_ROOT"
td_say "  перенесено файлов: $MOVED"

NEW_VERSION="$(tr -d ' \t\r\n' <"$TD_ROOT/VERSION")"

## ----------------------------------------------------------------------------
## Сборка и запуск. Миграции катит контейнер api при старте (SPEC.md 11.1)
## ----------------------------------------------------------------------------

td_say ""
td_say "Собираю образы…"
td_compose build ||
  td_die "Сборка образов не прошла. Файлы новой версии ($NEW_VERSION) уже на месте,
база не тронута и бэкап лежит здесь:
    $BACKUP_FILE
Исправьте причину и запустите: infra/scripts/start.sh"

td_say ""
"$TD_ROOT/infra/scripts/start.sh" ||
  td_die "Приложение не поднялось. Файлы версии $NEW_VERSION на месте, бэкап базы:
    $BACKUP_FILE
Логи: docker compose logs api"

API_PORT="$(td_env_value API_PORT)"
API_PORT="${API_PORT:-8000}"
REPORTED="$(td_fetch "http://127.0.0.1:$API_PORT/api/v1/version" /dev/stdout 2>/dev/null |
  sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1 || true)"

td_say ""
td_say "==============================================================="
td_say " Обновление завершено"
td_say "==============================================================="
td_say ""
td_say "  было            $CURRENT"
td_say "  стало           $NEW_VERSION   (файл VERSION)"
td_say "  приложение      ${REPORTED:-не ответило на /api/v1/version}"
td_say "  бэкап до этого  $BACKUP_FILE"
td_say ""
