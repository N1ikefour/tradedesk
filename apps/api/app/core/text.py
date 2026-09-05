"""Санитайзер свободного текста из внешних источников — X-21.

Коллектор, советник и CSV присылают строки, которые API кладёт в поля, видимые
пользователю: `trading_accounts.status_message` (heartbeat, SPEC.md 5.3) и
`sync_runs.error` (ингест, SPEC.md 3.4). Второе поле шире первого по последствиям:
`AccountResponse.status_message` отдаётся **каждым** маршрутом счетов, то есть попадает
в глобальный переключатель (SPEC.md 9.2) и на все экраны сразу.

Три вещи делаются здесь, и ни в одной нельзя доверять источнику:

1. известные секреты вырезаются `scrub_text` (X-02) — `COLLECTOR_TOKEN`, `MASTER_KEY`,
   пароли из `DATABASE_URL`/`REDIS_URL`: всё, что может попасть в текст ошибки на
   стороне, которая эти значения знает;
2. управляющие символы и переводы строк убираются — строка едет одной строкой и в
   JSON-лог, и в UI без разметки;
3. длина ограничивается — сообщение об ошибке не транспорт для дампа.

⚠️ Чего здесь **нет и быть не может: пароля самого счёта.** Он лежит в
`account_credentials` зашифрованным, а `CLAUDE.md` §5 разрешает расшифровку ровно в
одном месте — `GET /internal/collector/assignments`. Значит подстроку для вырезания
взять неоткуда, и этот канал закрывается только первым слоем X-21: коллектор не
пересылает дословный текст библиотеки MT5, а переводит его в известные формулировки.
Скраб здесь — второй слой, он не заменяет первый.
"""

from __future__ import annotations

import re

from app.core.logging import scrub_text

# Столько текста хватает, чтобы объяснить человеку, что случилось. Всё сверх — либо дамп,
# либо чужой вывод, и место ему в логах коллектора, а не в карточке счёта.
MAX_EXTERNAL_TEXT_LENGTH = 200

ELLIPSIS = "…"

# Тот же класс символов, что отвергают схемы auth, users и accounts.
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_WHITESPACE_RE = re.compile(r"\s+")


def sanitize_external_text(
    value: str | None, *, limit: int = MAX_EXTERNAL_TEXT_LENGTH
) -> str | None:
    """Текст, пригодный для показа пользователю. `None` — если показывать нечего.

    Скраб идёт **до** нормализации пробелов: замена управляющего символа внутри
    секрета разорвала бы подстроку, и `scrub_text` перестал бы её узнавать.
    Обрезка — последней, уже по вычищенному тексту: обрезать раньше значило бы
    оставить хвост секрета за границей проверки.
    """
    if value is None:
        return None
    scrubbed = scrub_text(value)
    collapsed = _WHITESPACE_RE.sub(" ", _CONTROL_RE.sub(" ", scrubbed)).strip()
    if not collapsed:
        return None
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - len(ELLIPSIS)].rstrip() + ELLIPSIS
