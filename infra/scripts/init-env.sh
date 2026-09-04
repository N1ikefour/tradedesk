#!/usr/bin/env sh
# `make init` — .env из .env.example с генерацией секретов (SPEC.md 11.2).
#
# ⚠️ Существующий .env не перезаписывается никогда. MASTER_KEY шифрует пароли брокерских
# счетов, и его потеря необратима: строки `account_credentials` не расшифровать ничем,
# резервная копия БД без ключа бесполезна. Повторный `make init` на рабочей установке,
# молча сгенерировавший новый ключ, стоил бы пользователю всех паролей счетов.
set -eu

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
EXAMPLE="$ROOT/.env.example"
TARGET="$ROOT/.env"

if [ -f "$TARGET" ]; then
  echo "make init: $TARGET уже существует — ничего не изменено." >&2
  echo "" >&2
  echo "Перезапись стёрла бы MASTER_KEY, а вместе с ним пароли всех брокерских счетов:" >&2
  echo "расшифровать их без ключа нельзя, дамп базы тут не поможет." >&2
  echo "" >&2
  echo "Нужен новый файл — сначала уберите старый вручную, осознанно:" >&2
  echo "    mv .env .env.bak && make init" >&2
  exit 1
fi

if [ ! -f "$EXAMPLE" ]; then
  echo "make init: не найден $EXAMPLE" >&2
  exit 1
fi

# Секреты берутся из криптостойкого источника. $RANDOM, дата и pid не годятся: MASTER_KEY
# защищает пароли счетов, а приложение вдобавок проверяет формат ключа при старте (S0-05)
# и в проде откажется грузиться на чём угодно, кроме base64 от ровно 32 байт.
if command -v openssl >/dev/null 2>&1; then
  gen_base64_32() { openssl rand -base64 32; }
  gen_hex() { openssl rand -hex "$1"; }
elif command -v python3 >/dev/null 2>&1; then
  gen_base64_32() { python3 -c "import base64,os;print(base64.b64encode(os.urandom(32)).decode())"; }
  gen_hex() { python3 -c "import os,sys;print(os.urandom(int(sys.argv[1])).hex())" "$1"; }
else
  echo "make init: нужен openssl или python3 — генерировать секреты нечем." >&2
  echo "На Windows openssl приходит вместе с Git for Windows (Git Bash)." >&2
  exit 1
fi

SECRET_KEY="$(gen_hex 32)"
MASTER_KEY="$(gen_base64_32)"
OTP_PEPPER="$(gen_hex 32)"
COLLECTOR_TOKEN="$(gen_hex 32)"
# hex, а не base64: пароль уезжает внутрь DATABASE_URL, где `+` и `/` пришлось бы экранировать.
POSTGRES_PASSWORD="$(gen_hex 24)"

TMP="$(mktemp "$ROOT/.env.tmp.XXXXXX")"
# Права до записи: файл не должен ни секунды существовать с секретами и чужим доступом.
chmod 600 "$TMP"
trap 'rm -f "$TMP"' EXIT INT TERM

awk \
  -v secret_key="$SECRET_KEY" \
  -v master_key="$MASTER_KEY" \
  -v otp_pepper="$OTP_PEPPER" \
  -v collector_token="$COLLECTOR_TOKEN" \
  -v postgres_password="$POSTGRES_PASSWORD" \
  '
BEGIN {
  v["SECRET_KEY"] = secret_key
  v["MASTER_KEY"] = master_key
  v["OTP_PEPPER"] = otp_pepper
  v["COLLECTOR_TOKEN"] = collector_token
  v["POSTGRES_PASSWORD"] = postgres_password
}
{
  line = $0
  if (match(line, /^[A-Za-z_][A-Za-z0-9_]*=/) == 0) { print line; next }
  name = substr(line, 1, RLENGTH - 1)
  rest = substr(line, RLENGTH + 1)
  hash = index(rest, "#")
  comment = (hash > 0) ? substr(rest, hash) : ""
  value = (hash > 0) ? substr(rest, 1, hash - 1) : rest
  if (name in v) {
    value = v[name]
  } else if (name == "DATABASE_URL") {
    # Пароль postgres живёт в двух местах — здесь и в POSTGRES_PASSWORD. Значение
    # подставляется в готовый URL из .env.example, чтобы форма URL осталась одна.
    sub(/^[ \t]+/, "", value); sub(/[ \t]+$/, "", value)
    if (sub(/:\/\/td:[^@]*@/, "://td:" postgres_password "@", value) == 0) {
      print "make init: DATABASE_URL в .env.example не той формы, пароль не подставлен" > "/dev/stderr"
      exit 3
    }
  } else {
    print line; next
  }
  print name "=" value (comment == "" ? "" : "   " comment)
}
' "$EXAMPLE" >"$TMP"

mv "$TMP" "$TARGET"
chmod 600 "$TARGET"
trap - EXIT INT TERM

echo "Создан $TARGET (права 600). Секреты сгенерированы, плейсхолдеры заменены."
echo ""
echo "⚠️  MASTER_KEY шифрует пароли брокерских счетов. Потеря ключа необратима —"
echo "    сохраните .env вместе с резервными копиями базы, иначе дамп бесполезен."
echo ""
echo "Дальше: make up"
