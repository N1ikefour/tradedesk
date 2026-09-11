#!/usr/bin/env sh
# `make init` — .env из .env.example с генерацией секретов (SPEC.md 11.2).
#
# ⚠️ Существующий .env не перезаписывается никогда. MASTER_KEY — ключ шифрования этой
# установки, и его потеря необратима: строки `account_credentials` не расшифровать ничем,
# резервная копия БД без ключа их не вернёт. Повторный `make init` на рабочей установке,
# молча сгенерировавший новый ключ, стоил бы пользователю всего, что этим ключом
# зашифровано.
set -eu

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
EXAMPLE="$ROOT/.env.example"
TARGET="$ROOT/.env"

# Отсюда берутся td_cmd и печать через printf. Своя копия определения платформы здесь
# разошлась бы с общей молча, а `echo` съел бы обратные слэши в `infra\scripts\…` (X-64).
TD_ROOT="$ROOT"
. "$ROOT/infra/scripts/common.sh"

INIT="$(td_cmd init)"

if [ -f "$TARGET" ]; then
  td_warn "$INIT: $TARGET уже существует — ничего не изменено."
  td_warn ""
  td_warn "Перезапись стёрла бы MASTER_KEY — ключ шифрования этой установки, второго"
  td_warn "экземпляра у него нет: зашифрованное им без ключа не прочитать, и дамп базы"
  td_warn "тут не поможет."
  td_warn ""
  td_warn "Нужен новый файл — сначала уберите старый вручную, осознанно:"
  if td_is_windows; then
    td_warn "    переименуйте .env в .env.bak, затем запустите $INIT"
  else
    td_warn "    mv .env .env.bak && $INIT"
  fi
  exit 1
fi

if [ ! -f "$EXAMPLE" ]; then
  td_warn "$INIT: не найден $EXAMPLE"
  exit 1
fi

# Секреты берутся из криптостойкого источника. $RANDOM, дата и pid не годятся: MASTER_KEY
# защищает данные установки, а приложение вдобавок проверяет формат ключа при старте (S0-05)
# и в проде откажется грузиться на чём угодно, кроме base64 от ровно 32 байт.
if command -v openssl >/dev/null 2>&1; then
  gen_base64_32() { openssl rand -base64 32; }
  gen_hex() { openssl rand -hex "$1"; }
elif command -v python3 >/dev/null 2>&1; then
  gen_base64_32() { python3 -c "import base64,os;print(base64.b64encode(os.urandom(32)).decode())"; }
  gen_hex() { python3 -c "import os,sys;print(os.urandom(int(sys.argv[1])).hex())" "$1"; }
else
  td_warn "$INIT: нужен openssl или python3 — генерировать секреты нечем."
  td_warn "На Windows openssl приходит вместе с Git for Windows (Git Bash)."
  exit 1
fi

SECRET_KEY="$(gen_hex 32)"
MASTER_KEY="$(gen_base64_32)"
OTP_PEPPER="$(gen_hex 32)"
COLLECTOR_TOKEN="$(gen_hex 32)"
# hex, а не base64: пароль уезжает внутрь DATABASE_URL, где `+` и `/` пришлось бы экранировать.
POSTGRES_PASSWORD="$(gen_hex 24)"

# Хвосты прошлых прогонов: trap ловит INT и TERM, но не SIGKILL и не отключение питания,
# а во временном файле лежат настоящие секреты. Права 600 и .gitignore не дают им утечь,
# но копиться мусору незачем — убираем перед тем, как создать свой.
rm -f "$ROOT"/.env.tmp.*

TMP="$(mktemp "$ROOT/.env.tmp.XXXXXX")"
# Права до записи: файл не должен ни секунды существовать с секретами и чужим доступом.
chmod 600 "$TMP"
trap 'rm -f "$TMP"' EXIT INT TERM

awk \
  -v init_cmd="$INIT" \
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
      print init_cmd ": DATABASE_URL в .env.example не той формы, пароль не подставлен" > "/dev/stderr"
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

td_say "Создан $TARGET (права 600). Секреты сгенерированы, плейсхолдеры заменены."
td_say ""
td_say "⚠️  MASTER_KEY — ключ шифрования этой установки, он создаётся один раз и здесь."
td_say "    Пароля брокерского счёта TradeDesk не спрашивает, так что шифровать ему пока"
td_say "    нечего, — но потеря ключа необратима: однажды зашифрованное им не расшифрует"
td_say "    никто. Храните .env вместе с резервными копиями базы: ключ лежит в нём."
td_say ""
td_say "Дальше: $(td_cmd up)"
