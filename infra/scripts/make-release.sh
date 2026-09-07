#!/usr/bin/env sh
# `make release VERSION=vX.Y.Z` — релизный zip-артефакт (ADR-0005, X-19).
#
# Что внутри: исходники, которые пользователь собирает у себя (`docker compose build`),
# а не готовые образы. Образы потребовали бы registry и авторизации в нём на машине, где
# мы экономим каждый шаг установки, а базовые образы всё равно качаются из сети — выигрыш
# получился бы только на сборке api, ценой второго места публикации и распухшего архива.
#
# Состав берётся у git, а не обходом файловой системы: `git ls-files` не видит .env,
# node_modules, .venv, backups и dist — они в .gitignore, и попасть в релиз не могут
# по построению, а не потому что кто-то не забыл их исключить. Проверка на запрещённые
# пути ниже всё равно есть: она ловит случай, когда .gitignore однажды поменяют.
#
# Версия. Приложение печатает её в /api/v1/version, а берёт из метаданных установленного
# пакета (importlib.metadata -> apps/api/pyproject.toml). Поэтому тег проставляется
# в pyproject внутри архива: собранный из архива образ отдаёт ровно ту версию, что
# написана на релизе. В репозитории версия не трогается — расходиться нечему.
set -eu

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

die() {
  echo "make release: $1" >&2
  exit 1
}

usage() {
  echo "Использование:" >&2
  echo "    make release VERSION=vX.Y.Z [OUT=<каталог>]" >&2
  echo "    infra/scripts/make-release.sh vX.Y.Z [<каталог>]" >&2
  echo "" >&2
  echo "Версия — тег релиза: vX.Y.Z или vX.Y.Z-rcN." >&2
}

RAW="${1:-}"
OUT_DIR="${2:-$ROOT/dist}"

if [ -z "$RAW" ]; then
  usage
  exit 2
fi

case "$RAW" in
  v*) TAG="$RAW" ;;
  *) TAG="v$RAW" ;;
esac

# Форма тега проверяется здесь, а не в CI: иначе релиз с опечаткой в имени доедет
# до страницы релизов и станет версией приложения.
if ! printf '%s' "$TAG" | grep -Eq '^v[0-9]+\.[0-9]+\.[0-9]+(-rc[0-9]+)?$'; then
  echo "make release: тег '$TAG' не той формы." >&2
  usage
  exit 2
fi

# PEP 440: 'v' не входит в версию пакета, а '-rc1' пишется как 'rc1'. Это та строка,
# которую вернёт /api/v1/version, — по ней T-02 сверяет установленную версию с новой.
VERSION="$(printf '%s' "${TAG#v}" | sed 's/-rc/rc/')"
PKG="tradedesk-$VERSION"

for tool in git zip unzip python3; do
  command -v "$tool" >/dev/null 2>&1 || die "нужен $tool, его нет в PATH."
done

if command -v sha256sum >/dev/null 2>&1; then
  sha256_of() { sha256sum "$1"; }
elif command -v shasum >/dev/null 2>&1; then
  sha256_of() { shasum -a 256 "$1"; }
else
  die "нечем посчитать sha256 — нужен sha256sum или shasum."
fi

git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1 ||
  die "$ROOT — не git-репозиторий, состав архива брать неоткуда."

WORK="$(mktemp -d "${TMPDIR:-/tmp}/tdrelease.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT INT TERM
DEST="$WORK/pkg/$PKG"
mkdir -p "$DEST"

## ----------------------------------------------------------------------------
## Состав
## ----------------------------------------------------------------------------

# -c: файлы под контролем версий, -o --exclude-standard: неотслеживаемые, но и не
# игнорируемые. Второе — ради честности локального прогона: в CI дерево чистое, а на
# машине разработчика архив должен собираться из того, что он видит перед собой.
# core.quotePath=false: иначе git отдаёт не-ASCII имена в escape-виде ("\320\267…"),
# и проверка ниже видит вместо кириллицы обычный ASCII — то есть пропускает ровно то,
# ради чего написана. Найдено прогоном с кириллическим именем файла, а не рассуждением.
git -C "$ROOT" -c core.quotePath=false ls-files -co --exclude-standard >"$WORK/all.txt"

UNTRACKED="$(git -C "$ROOT" -c core.quotePath=false ls-files -o --exclude-standard)"
if [ -n "$UNTRACKED" ]; then
  echo "⚠️  В архив попадут файлы вне git (не игнорируются, но и не закоммичены):" >&2
  printf '%s\n' "$UNTRACKED" | sed 's/^/      /' >&2
  echo "" >&2
fi

# Имена только ASCII. Windows-распаковщик Explorer читает имена без флага UTF-8 в кодовой
# странице системы и корёжит кириллицу; путь установки у первого пользователя и так
# кириллический (X-43), добавлять к этому кириллицу внутри архива незачем.
if LC_ALL=C grep -q '[^ -~]' "$WORK/all.txt"; then
  echo "make release: в именах файлов есть не-ASCII символы:" >&2
  LC_ALL=C grep '[^ -~]' "$WORK/all.txt" | sed 's/^/      /' >&2
  exit 1
fi
# Пробелы в путях сломали бы построчный разбор ниже. Их в проекте нет — фиксируем это.
if grep -q '[[:blank:]]' "$WORK/all.txt"; then
  die "в путях есть пробелы, разбор списка на это не рассчитан."
fi

# Что не уезжает пользователю. Всё остальное из git едет: правило «репозиторий минус
# перечисленное» короче списка включений и не забывает новый каталог при следующей задаче.
#   .github    — конфиг CI, у пользователя не работает;
#   .claude    — файлы ассистентов;
#   docs/tickets — внутренняя кухня: порты, worktree, черновики решений.
: >"$WORK/keep.txt"
while IFS= read -r path; do
  case "$path" in
    .github/* | .claude/* | .claude | docs/tickets/*) continue ;;
  esac
  printf '%s\n' "$path" >>"$WORK/keep.txt"
done <"$WORK/all.txt"

while IFS= read -r path; do
  dir="$(dirname "$path")"
  [ "$dir" = "." ] || mkdir -p "$DEST/$dir"
  # -p: сохраняются права. Без бита исполнения на infra/scripts/*.sh `make init`
  # на macOS и Linux падает с «permission denied» на первом же шаге установки.
  cp -p "$ROOT/$path" "$DEST/$path"
done <"$WORK/keep.txt"

## ----------------------------------------------------------------------------
## Версия
## ----------------------------------------------------------------------------

printf '%s\n' "$VERSION" >"$DEST/VERSION"

PYPROJECT="$DEST/apps/api/pyproject.toml"
[ -f "$PYPROJECT" ] || die "в архиве нет apps/api/pyproject.toml — проставлять версию некуда."

awk -v ver="$VERSION" '
  !stamped && /^version = "/ { print "version = \"" ver "\""; stamped = 1; next }
  { print }
  END { if (!stamped) {
    print "make release: в apps/api/pyproject.toml нет строки version = \"...\"" > "/dev/stderr"
    exit 3
  } }
' "$PYPROJECT" >"$PYPROJECT.stamped"
mv "$PYPROJECT.stamped" "$PYPROJECT"

# Проверка не грепом, а разбором toml: подставить строку в файл и не заметить, что она
# уехала не в ту секцию, — ровно тот случай, ради которого эта проверка написана.
python3 - "$PYPROJECT" "$VERSION" <<'PY'
import sys
import tomllib

path, want = sys.argv[1], sys.argv[2]
with open(path, "rb") as fh:
    data = tomllib.load(fh)
got = data.get("project", {}).get("version")
if got != want:
    sys.exit(f"версия в pyproject.toml — {got!r}, ожидалась {want!r}")
PY

## ----------------------------------------------------------------------------
## Что в архиве не имеет права оказаться
## ----------------------------------------------------------------------------

(cd "$DEST" && find . -mindepth 1 | sed 's|^\./||' | sort) >"$WORK/staged.txt"

FORBIDDEN='(^|/)(\.git|\.github|\.claude|node_modules|\.venv|venv|backups|dist|__pycache__|\.pytest_cache|\.mypy_cache|\.ruff_cache|htmlcov)(/|$)'
if grep -Eq "$FORBIDDEN" "$WORK/staged.txt"; then
  echo "make release: в архив попало то, чего там быть не должно:" >&2
  grep -E "$FORBIDDEN" "$WORK/staged.txt" | sed 's/^/      /' >&2
  exit 1
fi
if grep -Eq '(^|/)docs/tickets(/|$)' "$WORK/staged.txt"; then
  die "в архив попал docs/tickets."
fi
# .env, collector.env, .env.local и прочие формы. Разрешены только *.example.
if grep -E '(^|/)[^/]*\.env(\.[^/]*)?$' "$WORK/staged.txt" | grep -qv '\.example$'; then
  echo "make release: в архив попал файл окружения с секретами:" >&2
  grep -E '(^|/)[^/]*\.env(\.[^/]*)?$' "$WORK/staged.txt" | grep -v '\.example$' | sed 's/^/      /' >&2
  exit 1
fi

REQUIRED="VERSION docker-compose.yml Makefile .env.example .python-version SETUP.md README.md
apps/api/Dockerfile apps/api/pyproject.toml apps/api/docker-entrypoint.sh apps/api/alembic.ini
apps/web/package.json apps/web/package-lock.json apps/web/nginx.conf apps/web/Dockerfile
apps/collector-mt5/pyproject.toml packages/shared-schemas/ingest-deals.schema.json
infra/caddy/Caddyfile infra/scripts/init-env.sh infra/scripts/start.sh infra/scripts/start.bat
infra/scripts/stop.sh infra/scripts/stop.bat"
for req in $REQUIRED; do
  [ -e "$DEST/$req" ] || die "в архиве нет $req — установка по SETUP.md не пройдёт."
done

EXECUTABLES="infra/scripts/init-env.sh infra/scripts/start.sh infra/scripts/stop.sh
apps/api/docker-entrypoint.sh"
for exe in $EXECUTABLES; do
  [ -x "$DEST/$exe" ] || die "$exe без бита исполнения — make init/up на macOS и Linux упадёт."
done

## ----------------------------------------------------------------------------
## Упаковка
## ----------------------------------------------------------------------------

mkdir -p "$OUT_DIR"
OUT_DIR="$(cd "$OUT_DIR" && pwd)"
ZIP="$OUT_DIR/$PKG.zip"
rm -f "$ZIP" "$ZIP.sha256"

# Один каталог верхнего уровня внутри архива: распаковка в Загрузки не должна рассыпать
# три сотни файлов по каталогу. -X убирает uid/gid и Finder-атрибуты, права остаются.
(cd "$WORK/pkg" && zip -q -r -X "$ZIP" "$PKG")

# Архив, который никто не распаковывал, — предположение. Проверяется то, ради чего zip
# и собирался: он читается, права на скриптах пережили упаковку, версия внутри — та самая.
unzip -tq "$ZIP" >/dev/null || die "собранный архив не проходит проверку целостности."
mkdir -p "$WORK/verify"
unzip -q "$ZIP" -d "$WORK/verify"
for exe in $EXECUTABLES; do
  [ -x "$WORK/verify/$PKG/$exe" ] ||
    die "после распаковки $exe потерял бит исполнения."
done
[ "$(cat "$WORK/verify/$PKG/VERSION")" = "$VERSION" ] || die "VERSION в архиве не совпал."

(cd "$OUT_DIR" && sha256_of "$PKG.zip" >"$PKG.zip.sha256")

SIZE="$(du -h "$ZIP" | cut -f1 | tr -d ' ')"
FILES="$(wc -l <"$WORK/keep.txt" | tr -d ' ')"

echo ""
echo "Собран $ZIP"
echo ""
echo "  тег           $TAG"
echo "  версия        $VERSION   (её вернёт /api/v1/version)"
echo "  файлов        $FILES + VERSION"
echo "  размер        $SIZE"
echo "  контрольная   $(cut -d' ' -f1 <"$ZIP.sha256")"
echo ""
echo "Внутри один каталог $PKG/."
echo "Проверить у себя: распаковать в пустую папку и пройти SETUP.md."
