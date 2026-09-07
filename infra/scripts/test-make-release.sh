#!/usr/bin/env sh
# Тесты make-release.sh (X-19). Единственный страж релизного артефакта — он сам:
# ни один другой прогон в проекте не смотрит, что уезжает пользователю. Сломанная
# регулярка запрещённых путей или отвалившаяся проверка симлинков не покраснели бы
# нигде — архив собрался бы и опубликовался.
#
# Каждый негативный случай ниже привязан к одной проверке в скрипте: снимите проверку —
# соответствующий случай станет красным. Позитивные случаи держат обратное — что проверки
# не запрещают лишнего (черновик тикета с кириллицей в имени релиз не блокирует).
#
# Репозиторий берётся синтетический, а не рабочий: тесту нужно коммитить симлинки, .env
# и node_modules, чего в настоящем дереве делать нельзя.
set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
SCRIPT="$HERE/make-release.sh"

[ -x "$SCRIPT" ] || {
  echo "test-make-release: $SCRIPT не найден или без бита исполнения." >&2
  exit 2
}

for tool in git zip unzip python3 make; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "test-make-release: нужен $tool, его нет в PATH." >&2
    exit 2
  }
done

WORK="$(mktemp -d "${TMPDIR:-/tmp}/tdreltest.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT INT TERM
OUT="$WORK/out.txt"

PASSED=0
FAILED=0

ok() {
  PASSED=$((PASSED + 1))
  printf '  ok      %s\n' "$1"
}

bad() {
  FAILED=$((FAILED + 1))
  printf '  ПРОВАЛ  %s\n' "$1"
  [ -f "$OUT" ] && sed 's/^/          | /' "$OUT"
  return 0
}

## ----------------------------------------------------------------------------
## Синтетический репозиторий: минимум, который make-release.sh считает установкой
## ----------------------------------------------------------------------------

fixture() {
  repo="$WORK/$1"
  mkdir -p "$repo/apps/api" "$repo/apps/web" "$repo/apps/collector-mt5" \
    "$repo/packages/shared-schemas" "$repo/infra/caddy" "$repo/infra/scripts" "$repo/docs"

  for f in docker-compose.yml Makefile .env.example SETUP.md README.md \
    apps/api/Dockerfile apps/api/alembic.ini apps/web/package.json \
    apps/web/package-lock.json apps/web/nginx.conf apps/web/Dockerfile \
    packages/shared-schemas/ingest-deals.schema.json infra/caddy/Caddyfile \
    infra/scripts/start.bat infra/scripts/stop.bat; do
    printf 'stub\n' >"$repo/$f"
  done
  printf '3.12\n' >"$repo/.python-version"
  printf '[project]\nname = "tradedesk-api"\nversion = "0.0.0"\n' >"$repo/apps/api/pyproject.toml"
  printf '[project]\nname = "tradedesk-collector"\nversion = "0.0.0"\n' \
    >"$repo/apps/collector-mt5/pyproject.toml"
  for f in infra/scripts/init-env.sh infra/scripts/start.sh infra/scripts/stop.sh \
    apps/api/docker-entrypoint.sh; do
    printf '#!/bin/sh\n' >"$repo/$f"
    chmod +x "$repo/$f"
  done

  cp -p "$SCRIPT" "$repo/infra/scripts/make-release.sh"

  git -C "$repo" init -q -b main
  git -C "$repo" config user.email "test@example.invalid"
  git -C "$repo" config user.name "test"
  git -C "$repo" config commit.gpgsign false
  git -C "$repo" add -A
  git -C "$repo" commit -qm fixture
  printf '%s' "$repo"
}

commit_all() {
  git -C "$1" add -A
  git -C "$1" commit -qm change
}

# env, а не `RELEASE_ALLOW_UNTRACKED=1 release …`: присваивание перед вызовом ФУНКЦИИ
# в POSIX-шелле остаётся в окружении и после возврата, то есть протекло бы во все
# следующие случаи и молча их зазеленило.
release() {
  repo="$1"
  shift
  env -u RELEASE_ALLOW_UNTRACKED "$repo/infra/scripts/make-release.sh" "$@" >"$OUT" 2>&1
}

release_allow_untracked() {
  repo="$1"
  shift
  env RELEASE_ALLOW_UNTRACKED=1 "$repo/infra/scripts/make-release.sh" "$@" >"$OUT" 2>&1
}

expect_fail() {
  name="$1"
  want="$2"
  repo="$3"
  shift 3
  if release "$repo" "$@"; then
    bad "$name — сборка прошла, а должна была упасть"
    return 0
  fi
  if grep -qF "$want" "$OUT"; then
    ok "$name"
  else
    # Скобки обязательны: без них закрывающая кавычка-ёлочка прилипает к имени
    # переменной, и под `set -u` падает сам тест — ровно на той ветке, ради которой
    # он написан.
    bad "$name — упало, но не на том: в выводе нет «${want}»"
  fi
}

expect_ok() {
  name="$1"
  repo="$2"
  shift 2
  if release "$repo" "$@"; then
    ok "$name"
  else
    bad "$name — сборка упала"
  fi
}

zip_paths() {
  unzip -Z1 "$1"
}

echo ""
echo "make-release.sh"
echo ""

## ----------------------------------------------------------------------------
## Позитив: архив собирается и внутри него то, что обещано
## ----------------------------------------------------------------------------

repo="$(fixture happy)"
if release "$repo" v1.2.3 "$repo/out"; then
  ZIP="$repo/out/tradedesk-1.2.3.zip"
  if [ -f "$ZIP" ] && [ -f "$ZIP.sha256" ]; then
    ok "собран zip и sha256 рядом"
  else
    bad "нет zip или sha256"
  fi
  if zip_paths "$ZIP" | grep -q '^tradedesk-1\.2\.3/docker-compose\.yml$'; then
    ok "внутри один каталог tradedesk-1.2.3/"
  else
    bad "структура архива не та"
  fi
  rm -rf "$WORK/x" && mkdir -p "$WORK/x" && unzip -q "$ZIP" -d "$WORK/x"
  if [ "$(cat "$WORK/x/tradedesk-1.2.3/VERSION")" = "1.2.3" ]; then
    ok "VERSION в архиве равен версии тега"
  else
    bad "VERSION в архиве не тот"
  fi
  if grep -q '^version = "1.2.3"$' "$WORK/x/tradedesk-1.2.3/apps/api/pyproject.toml"; then
    ok "версия проставлена в apps/api/pyproject.toml"
  else
    bad "pyproject не проштампован"
  fi
  if [ -x "$WORK/x/tradedesk-1.2.3/infra/scripts/start.sh" ]; then
    ok "бит исполнения пережил распаковку"
  else
    bad "start.sh после распаковки без бита исполнения"
  fi
else
  bad "базовая сборка упала"
fi

# Тег без 'v' и rc-форма — обе разрешены, обе дают версию по PEP 440.
repo="$(fixture bare-tag)"
expect_ok "тег без 'v' принимается" "$repo" 1.2.3 "$repo/out"
repo="$(fixture rc)"
if release "$repo" v1.2.3-rc1 "$repo/out" && [ -f "$repo/out/tradedesk-1.2.3rc1.zip" ]; then
  ok "rc-тег даёт версию 1.2.3rc1"
else
  bad "rc-тег собрался не так"
fi

## ----------------------------------------------------------------------------
## Отсев внутренних каталогов — и то, что он идёт ДО проверок имён
## ----------------------------------------------------------------------------

repo="$(fixture tickets)"
mkdir -p "$repo/docs/tickets" "$repo/.github/workflows" "$repo/.claude"
printf 'draft\n' >"$repo/docs/tickets/черновик решения.md"
printf 'draft\n' >"$repo/.github/workflows/ci.yml"
printf 'draft\n' >"$repo/.claude/notes.md"
commit_all "$repo"
if release "$repo" v1.2.3 "$repo/out"; then
  ok "кириллица и пробел в docs/tickets релиз не блокируют"
  if zip_paths "$repo/out/tradedesk-1.2.3.zip" | grep -Eq 'docs/tickets|\.github|\.claude'; then
    bad "внутренние каталоги уехали в архив"
  else
    ok "docs/tickets, .github и .claude в архив не попали"
  fi
else
  bad "черновик тикета заблокировал релиз"
fi

## ----------------------------------------------------------------------------
## Негатив: каждая проверка скрипта — свой случай
## ----------------------------------------------------------------------------

# Симлинк наружу. cp -p без -P разыменовывает его, и содержимое чужого файла уезжает
# в архив под безобидным именем — проверка на *.env такое не ловит.
printf 'AWS_SECRET=REALSECRET123\n' >"$WORK/outside-secret.txt"
repo="$(fixture symlink-tracked)"
ln -s "$WORK/outside-secret.txt" "$repo/notes.txt"
commit_all "$repo"
expect_fail "симлинк наружу — отказ" "символические ссылки" "$repo" v1.2.3 "$repo/out"
if [ -f "$repo/out/tradedesk-1.2.3.zip" ]; then
  bad "после отказа на симлинке архив всё-таки собрался"
else
  ok "после отказа на симлинке архива нет"
fi

repo="$(fixture symlink-untracked)"
ln -s "$WORK/outside-secret.txt" "$repo/notes.txt"
expect_fail "неотслеживаемый файл — отказ" "вне git" "$repo" v1.2.3 "$repo/out"
if release_allow_untracked "$repo" v1.2.3 "$repo/out"; then
  bad "RELEASE_ALLOW_UNTRACKED снял и проверку симлинков"
elif grep -qF "символические ссылки" "$OUT"; then
  ok "RELEASE_ALLOW_UNTRACKED не снимает проверку симлинков"
else
  bad "упало, но не на симлинке"
fi

repo="$(fixture untracked)"
printf 'заметка\n' >"$repo/scratch.md"
expect_fail "неотслеживаемый файл без флага — отказ" "вне git" "$repo" v1.2.3 "$repo/out"
if release_allow_untracked "$repo" v1.2.3 "$repo/out" &&
  zip_paths "$repo/out/tradedesk-1.2.3.zip" | grep -q 'scratch\.md$'; then
  ok "с RELEASE_ALLOW_UNTRACKED=1 файл едет в архив осознанно"
else
  bad "флаг RELEASE_ALLOW_UNTRACKED не работает"
fi

repo="$(fixture envfile)"
printf 'SECRET_KEY=hunter2\n' >"$repo/apps/api/.env"
commit_all "$repo"
expect_fail "файл окружения — отказ" "файл окружения с секретами" "$repo" v1.2.3 "$repo/out"

repo="$(fixture forbidden)"
mkdir -p "$repo/node_modules"
printf 'x\n' >"$repo/node_modules/index.js"
commit_all "$repo"
expect_fail "запрещённый каталог — отказ" "чего там быть не должно" "$repo" v1.2.3 "$repo/out"

repo="$(fixture nonascii)"
printf 'x\n' >"$repo/docs/решение.md"
commit_all "$repo"
expect_fail "не-ASCII в имени файла архива — отказ" "не-ASCII" "$repo" v1.2.3 "$repo/out"

repo="$(fixture blanks)"
printf 'x\n' >"$repo/docs/two words.md"
commit_all "$repo"
expect_fail "пробел в пути — отказ" "пробелы" "$repo" v1.2.3 "$repo/out"

repo="$(fixture missing)"
rm "$repo/Makefile"
commit_all "$repo"
expect_fail "нет обязательного файла — отказ" "в архиве нет Makefile" "$repo" v1.2.3 "$repo/out"

repo="$(fixture noexec)"
chmod -x "$repo/infra/scripts/start.sh"
commit_all "$repo"
expect_fail "скрипт без бита исполнения — отказ" "без бита исполнения" "$repo" v1.2.3 "$repo/out"

repo="$(fixture badver)"
expect_fail "ведущий ноль в версии — отказ" "не той формы" "$repo" v01.2.3 "$repo/out"
expect_fail "мусорный тег — отказ" "не той формы" "$repo" "v1.2" "$repo/out"
expect_fail "пустая версия — отказ" "Использование" "$repo"

## ----------------------------------------------------------------------------
## Грязное дерево — предупреждение, но не отказ
## ----------------------------------------------------------------------------

repo="$(fixture dirty)"
printf 'дописано\n' >>"$repo/SETUP.md"
if release "$repo" v1.2.3 "$repo/out" && grep -qF "Дерево грязное" "$OUT"; then
  ok "изменённый отслеживаемый файл упомянут в выводе"
else
  bad "правка в SETUP.md уехала в архив молча"
fi

## ----------------------------------------------------------------------------
## Значение VERSION не должно доезжать до sh как код (Makefile, а не скрипт)
## ----------------------------------------------------------------------------

CANARY="$WORK/canary"
rm -f "$CANARY"
# Скрипт отказывает по форме тега раньше любых действий с деревом, поэтому прогон
# против настоящего репозитория ничего в нём не трогает и архива не создаёт.
if env -u MAKEFLAGS -u MFLAGS make -C "$ROOT" release \
  VERSION="v9.9.9\"; : >$CANARY; echo \"" >"$OUT" 2>&1; then
  bad "make release принял тег с инъекцией"
elif [ -e "$CANARY" ]; then
  bad "make release ИСПОЛНИЛ подставленное в VERSION"
elif grep -qF "не той формы" "$OUT"; then
  ok "make release: значение VERSION не исполняется шеллом"
else
  bad "make release упал, но не на проверке формы тега"
fi

## ----------------------------------------------------------------------------

echo ""
echo "  пройдено $PASSED, провалено $FAILED"
echo ""
[ "$FAILED" -eq 0 ] || exit 1
