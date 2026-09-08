"""Всё, что коллектор говорит человеку, и таблица кодов MT5 — SPEC.md 8.2.

Коллектор работает на чужой машине, до которой мы не дотянемся ни отладчиком, ни
логами сервера. Единственный канал диагностики — строка, которую он напечатает в файл
и пришлёт в `POST /ingest/heartbeat`, откуда она попадёт в `status_message` на экране
счёта. Поэтому тексты собраны здесь списком, а не разбросаны по местам возникновения:
так их видно целиком, и один тест проверяет язык, длину и то, что в них не подставится
пароль.

⚠️ **Числовые коды взяты из документации MetaTrader5, а не из терминала.** Запустить
терминал на машине разработки нечем (macOS), поэтому ни один код здесь не наблюдался.
Описания из `mt5.last_error()[1]` тем более: по ним построены всего два уточнения, и оба
помечены как непроверенные. Первый прогон на Windows обязан сверить таблицу с тем, что
отдаёт настоящий терминал.
"""

from __future__ import annotations

from typing import Final, Literal

# Потолок сообщения. `app/core/text.py` режет внешний текст до 200 символов при записи в
# `trading_accounts.status_message`, то есть длинное сообщение доедет до экрана обрезанным
# на полуслове. Режем здесь и по границе слова — что показать, решает автор текста, а не
# случайная позиция символа.
MAX_MESSAGE_LENGTH: Final = 200

ELLIPSIS: Final = "…"


def fit(text: str, *, limit: int = MAX_MESSAGE_LENGTH) -> str:
    """Уложить сообщение в потолок хранения, обрезая по границе слова."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    head = collapsed[: limit - len(ELLIPSIS)]
    cut = head.rsplit(" ", 1)[0] if " " in head else head
    return f"{cut}{ELLIPSIS}"


# --------------------------------------------------------------------------------------
# Коды MetaTrader5 (`mt5.last_error()`), из документации библиотеки.
# --------------------------------------------------------------------------------------

RES_S_OK: Final = 1
RES_E_FAIL: Final = -1
RES_E_INVALID_PARAMS: Final = -2
RES_E_NO_MEMORY: Final = -3
RES_E_NOT_FOUND: Final = -4
RES_E_INVALID_VERSION: Final = -5
RES_E_AUTH_FAILED: Final = -6
RES_E_UNSUPPORTED: Final = -7
RES_E_AUTO_TRADING_DISABLED: Final = -8
RES_E_INTERNAL_FAIL: Final = -10000
RES_E_INTERNAL_FAIL_SEND: Final = -10001
RES_E_INTERNAL_FAIL_RECEIVE: Final = -10002
RES_E_INTERNAL_FAIL_INIT: Final = -10003
RES_E_INTERNAL_FAIL_CONNECT: Final = -10004
RES_E_INTERNAL_FAIL_TIMEOUT: Final = -10005

# Где именно оборвалось. Один и тот же код значит разное на разных шагах: -4 при входе —
# «терминал не нашёл счёт», -4 при запросе истории — «за период сделок нет».
Stage = Literal["connect", "history", "positions", "account_info", "tick"]


# --------------------------------------------------------------------------------------
# Тексты. Каждый обязан отвечать на два вопроса: что случилось и что человеку делать.
# --------------------------------------------------------------------------------------

NOT_WINDOWS: Final = (
    "Коллектор MT5 работает только на Windows: библиотеки MetaTrader5 под {system} "
    "не существует. Запустите коллектор на машине с терминалом."
)

MT5_PACKAGE_MISSING: Final = (
    "Библиотека MetaTrader5 не установлена. Поставьте её командой "
    "pip install -e .[mt5] в папке apps/collector-mt5."
)

TERMINAL_EXE_MISSING: Final = (
    "Не найден файл терминала MetaTrader 5: {path}. Проверьте MT5_TERMINAL_EXE в collector.env."
)

PORTABLE_COPY_FAILED: Final = (
    "Не удалось подготовить рабочую копию терминала в {path}: {reason}. Проверьте права "
    "на папку из MT5_PORTABLE_ROOT."
)

# X-43: у первого пользователя имя папки профиля кириллицей, и Docker из такого пути не
# собирается вовсе (X-54). MetaTrader5 — обёртка над нативным кодом, и как он обходится с
# путями вне латиницы, мы не проверяли. Это предупреждение, а не отказ: запретить путь,
# который, возможно, работает, значит выдумать ограничение.
NON_ASCII_PATH: Final = (
    "Путь {path} содержит буквы вне латиницы. Терминал MetaTrader 5 — нативная программа "
    "и такие пути читает не всегда. Надёжнее путь вида C:\\td-terminals."
)

AUTH_FAILED: Final = (
    "Неверный пароль инвестора. Терминал не пустил на счёт {login} на сервере «{server}» — "
    "проверьте пароль и имя сервера в карточке счёта."
)

# ⚠️ Непроверено: по какому коду и с каким текстом терминал сообщает о неизвестном имени
# сервера, мы не видели. Ветка включается по подстроке описания и обязана быть сверена на
# Windows — до тех пор такой случай выглядит как AUTH_FAILED.
SERVER_NOT_FOUND: Final = (
    "Сервер брокера «{server}» не найден. Проверьте имя сервера в карточке счёта: оно "
    "пишется ровно так, как в терминале."
)

INVALID_PARAMS: Final = (
    "Терминал отказался от параметров подключения. Проверьте номер счёта и имя сервера "
    "в карточке счёта."
)

NO_MEMORY: Final = (
    "Не хватило памяти на запуск терминала. Закройте лишние программы или уменьшите "
    "MAX_ACCOUNTS в collector.env: один терминал занимает 300–400 МБ."
)

ACCOUNT_NOT_FOUND: Final = (
    "Терминал не нашёл счёт {login} на сервере «{server}». Проверьте номер счёта."
)

INVALID_VERSION: Final = (
    "Сборка терминала MetaTrader 5 не подходит библиотеке коллектора. Обновите терминал "
    "до последней версии."
)

UNSUPPORTED: Final = (
    "Терминал не поддерживает вызов, который делает коллектор. Скорее всего, он слишком "
    "старой сборки — обновите терминал."
)

AUTO_TRADING_DISABLED: Final = (
    "В терминале выключён автотрейдинг. Коллектор только читает историю, но библиотека "
    "MetaTrader5 без него не работает: включите его в настройках терминала."
)

TERMINAL_WONT_START: Final = (
    "Терминал MetaTrader 5 не запускается: {path}. Запустите его вручную один раз и "
    "проверьте MT5_TERMINAL_EXE в collector.env."
)

TERMINAL_LOST: Final = (
    "Оборвалась связь с терминалом MetaTrader 5: он закрылся или не успел подняться. "
    "Коллектор переподключится сам."
)

TERMINAL_TIMEOUT: Final = (
    "Терминал MetaTrader 5 не ответил вовремя. Обычно это медленный первый запуск или "
    "занятая машина; коллектор повторит попытку."
)

NO_HISTORY: Final = (
    "Терминал не отдал историю сделок за запрошенный период. Если счёт не пустой, дайте "
    "терминалу догрузить историю с сервера брокера."
)

# Последний рубеж: код, которого нет в таблице. Текст терминала подставляется как есть,
# чтобы человек мог назвать его нам, — своих слов у нас для него нет.
UNKNOWN_MT5_ERROR: Final = (
    "Терминал MetaTrader 5 вернул ошибку {code}, которой коллектор не знает. "
    "Текст терминала: {description}"
)

NOT_USD: Final = (
    "Счёт не в USD: валюта счёта {currency}. TradeDesk v1 работает только с долларовыми "
    "счетами, синхронизация этого счёта остановлена."
)

OFFSET_UNKNOWN: Final = (
    "Не удалось определить смещение часов сервера брокера: свежей котировки нет. "
    "Синхронизация продолжится, когда рынок откроется."
)

ASSIGNMENT_MISSING: Final = (
    "Счёт {account_id} не выдан этому коллектору. Проверьте, что счёт не на паузе и не "
    "в архиве, и что COLLECTOR_ID в collector.env тот же, что закреплён за счётом."
)

API_UNREACHABLE: Final = (
    "TradeDesk не отвечает по адресу {api_url}: {reason}. Сделки не потеряны — коллектор "
    "отправит их следующей попыткой."
)

API_REFUSED: Final = (
    "TradeDesk не принял сделки: {message} Коллектор повторит отправку через минуту; "
    "если сообщение держится, причина не в связи."
)

DEALS_DROPPED: Final = (
    "Терминал отдал {count} сделок, которые TradeDesk не примет (первая — тикет {ticket}: "
    "{reason}). Остальные сделки отправлены; расскажите об этом разработчику."
)

CONFIG_INVALID: Final = "Ошибка в collector.env: {problems}"

RUNNING: Final = "Синхронизация идёт."

STOPPED: Final = "Коллектор остановлен."


def not_windows(system: str) -> str:
    return fit(NOT_WINDOWS.format(system=system))


def non_ascii_path(path: str) -> str:
    return fit(NON_ASCII_PATH.format(path=path))


def not_usd(currency: str) -> str:
    return fit(NOT_USD.format(currency=currency))


# Подстроки описаний `last_error()`, по которым уточняется код. Список нарочно короткий:
# каждая строка здесь — догадка о тексте, который мы не видели, а догадка, выдающая себя
# за факт, хуже отсутствия ветки. Проверяется на Windows и дополняется наблюдениями.
_DESCRIPTION_HINTS: Final[tuple[tuple[str, str], ...]] = (
    ("ipc initialize failed", TERMINAL_WONT_START),
    ("not found", SERVER_NOT_FOUND),
)


def describe_mt5_failure(
    code: int,
    description: str,
    *,
    stage: Stage,
    server: str = "",
    login: int = 0,
    terminal_path: str = "",
) -> str:
    """Код и текст терминала → фраза, по которой человек поймёт, что чинить.

    Чистая функция: ни терминала, ни сети. Отсюда и берётся `message` heartbeat'а.
    """
    text = _by_code(code, stage=stage, description=description)
    if text is None:
        text = _by_description(description, stage=stage)
    if text is None:
        text = UNKNOWN_MT5_ERROR
    return fit(
        text.format(
            code=code,
            description=description or "пусто",
            server=server or "—",
            login=login,
            path=terminal_path or "—",
        )
    )


def _by_code(code: int, *, stage: Stage, description: str) -> str | None:
    if code == RES_E_AUTH_FAILED:
        # Отличить неверный пароль от неверного имени сервера нечем: терминал отвечает
        # одним кодом, а описания мы не наблюдали. Ведём паролем — он ошибается чаще, и
        # имя сервера в тексте всё равно названо.
        if _hints_at(description, "not found"):
            return SERVER_NOT_FOUND
        return AUTH_FAILED
    if code == RES_E_INVALID_PARAMS:
        return INVALID_PARAMS
    if code == RES_E_NO_MEMORY:
        return NO_MEMORY
    if code == RES_E_NOT_FOUND:
        return NO_HISTORY if stage == "history" else ACCOUNT_NOT_FOUND
    if code == RES_E_INVALID_VERSION:
        return INVALID_VERSION
    if code == RES_E_UNSUPPORTED:
        return UNSUPPORTED
    if code == RES_E_AUTO_TRADING_DISABLED:
        return AUTO_TRADING_DISABLED
    if code == RES_E_INTERNAL_FAIL_INIT:
        return TERMINAL_WONT_START
    if code == RES_E_INTERNAL_FAIL_TIMEOUT:
        return TERMINAL_TIMEOUT
    if code in (
        RES_E_INTERNAL_FAIL,
        RES_E_INTERNAL_FAIL_SEND,
        RES_E_INTERNAL_FAIL_RECEIVE,
        RES_E_INTERNAL_FAIL_CONNECT,
    ):
        return TERMINAL_LOST
    return None


def _by_description(description: str, *, stage: Stage) -> str | None:
    for needle, text in _DESCRIPTION_HINTS:
        if _hints_at(description, needle):
            # «not found» без кода авторизации на шаге входа — это про сервер, а на
            # остальных шагах — про историю, и путать их нельзя.
            if text is SERVER_NOT_FOUND and stage != "connect":
                continue
            return text
    return None


def _hints_at(description: str, needle: str) -> bool:
    return needle in description.casefold()
