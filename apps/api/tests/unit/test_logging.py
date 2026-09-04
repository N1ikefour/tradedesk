"""Логи не выдают секретов — ни по имени ключа, ни внутри текста исключения."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass

import pytest
import structlog
from fastapi import FastAPI

from app.core import logging as logging_module
from app.core.config import Settings
from app.core.logging import (
    MAX_SCRUB_ITEMS,
    MAX_SCRUB_NODES,
    REDACTED,
    UNSCANNED,
    configure_logging,
    get_logger,
    register_secret_values,
    scrub_text,
    scrub_values,
)

DSN_WITH_PASSWORD = "postgresql://td:hunter2@db.internal:5432/td"
DSN_WITH_QUERY_PASSWORD = "postgresql+asyncpg://td@db.internal:5432/td?password=ПАРОЛЬ-БД"
REDIS_URL_WITH_PASSWORD = "redis://:ПАРОЛЬ-REDIS@redis.internal:6379/0"


@dataclass(frozen=True)
class Connection:
    """Произвольный объект в аргументе лога: рендерер печатает его через repr()."""

    dsn: str


@pytest.fixture(autouse=True)
def _reset_registered_secrets() -> None:
    register_secret_values([])


def test_scrub_text_hides_password_in_dsn() -> None:
    scrubbed = scrub_text(f"connection failed: {DSN_WITH_PASSWORD}")

    assert "hunter2" not in scrubbed
    # Хост остаётся: без него сообщение бесполезно для диагностики.
    assert "db.internal" in scrubbed
    assert REDACTED in scrubbed


def test_scrub_text_hides_registered_secret_value() -> None:
    register_secret_values(["super-secret-token"])

    assert "super-secret-token" not in scrub_text("token=super-secret-token")


def test_scrub_text_ignores_short_values() -> None:
    """Короткая подстрока встречается в осмысленном тексте — вырезать её нельзя."""
    register_secret_values(["td"])

    assert scrub_text("подключение к td") == "подключение к td"


def test_log_line_is_json_and_censors_secret_keys(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging()
    get_logger("test").info("probe", secret_key="значение-секрета", host="localhost")

    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])

    assert line["event"] == "probe"
    assert line["secret_key"] == REDACTED
    assert line["host"] == "localhost"


def test_traceback_does_not_leak_dsn_password(capsys: pytest.CaptureFixture[str]) -> None:
    """Регрессия на находку ревью S0-02: цензура по имени ключа не спасала от текста
    исключения — format_exc_info рендерит traceback в поле `exception`."""
    configure_logging()
    try:
        raise RuntimeError(f"connection failed: {DSN_WITH_PASSWORD}")
    except RuntimeError:
        get_logger("test").exception("api.unhandled_exception")

    output = capsys.readouterr().out

    assert "hunter2" not in output
    assert "connection failed" in output


def test_secret_key_inside_nested_dict_is_censored(capsys: pytest.CaptureFixture[str]) -> None:
    """S0-04 логирует тело запроса: `password` и `token` приезжают вложенным словарём,
    а по имени ключа цензура смотрела только верхний уровень."""
    configure_logging()
    get_logger("test").info("body", request={"body": {"password": "hunter2"}, "path": "/login"})

    output = capsys.readouterr().out
    line = json.loads(output.strip().splitlines()[-1])

    assert "hunter2" not in output
    assert line["request"]["body"]["password"] == REDACTED
    assert line["request"]["path"] == "/login"


def test_secret_key_inside_list_of_dicts_is_censored(capsys: pytest.CaptureFixture[str]) -> None:
    """`details` ошибки валидации — список объектов; секретное поле лежит внутри элемента."""
    configure_logging()
    get_logger("test").info("details", items=[{"field": "password", "password": "hunter2"}])

    output = capsys.readouterr().out
    line = json.loads(output.strip().splitlines()[-1])

    assert "hunter2" not in output
    assert line["items"][0]["password"] == REDACTED
    assert line["items"][0]["field"] == "password"


def test_secret_key_censors_whole_nested_value(capsys: pytest.CaptureFixture[str]) -> None:
    """Под секретным ключом бывает не строка: список вырезается целиком, а не поэлементно."""
    configure_logging()
    get_logger("test").info("multi", auth={"token": ["hunter2", "hunter3"]})

    output = capsys.readouterr().out
    line = json.loads(output.strip().splitlines()[-1])

    assert "hunter2" not in output
    assert line["auth"]["token"] == REDACTED


def test_censor_does_not_mutate_caller_structure(capsys: pytest.CaptureFixture[str]) -> None:
    """Логирование не вправе портить объект вызывающего кода — он живёт дальше в запросе."""
    body: dict[str, object] = {"password": "hunter2"}
    payload = {"body": body}

    configure_logging()
    get_logger("test").info("body", request=payload)

    assert body["password"] == "hunter2"
    assert "hunter2" not in capsys.readouterr().out


def test_explicit_exc_info_tuple_survives_censoring(capsys: pytest.CaptureFixture[str]) -> None:
    """Цензура стоит до format_exc_info и пересобирает кортежи — `exc_info` кортежем обязан
    дойти до рендера traceback, иначе исключение потеряется по дороге."""
    configure_logging()
    try:
        raise RuntimeError(f"connection failed: {DSN_WITH_PASSWORD}")
    except RuntimeError:
        get_logger("test").info("explicit", exc_info=sys.exc_info())

    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])

    assert "connection failed" in line["exception"]
    assert "hunter2" not in line["exception"]


def test_secret_in_nested_dict_is_scrubbed(capsys: pytest.CaptureFixture[str]) -> None:
    """Тело запроса и `details` ошибки валидации приезжают в лог вложенной структурой."""
    configure_logging()
    get_logger("test").info("nested", payload={"db": {"dsn": DSN_WITH_PASSWORD}})

    output = capsys.readouterr().out

    assert "hunter2" not in output
    assert "db.internal" in output


def test_secret_in_list_is_scrubbed(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging()
    get_logger("test").info("in_list", items=[DSN_WITH_PASSWORD])

    output = capsys.readouterr().out

    assert "hunter2" not in output
    assert "db.internal" in output


def test_cyclic_structure_does_not_break_logging(capsys: pytest.CaptureFixture[str]) -> None:
    """Циклическую структуру логгер обязан пережить: без ограничения глубины обход уходит
    в рекурсию, а JSON-рендер падает на circular reference — записи не будет вовсе."""
    cycle: dict[str, object] = {"dsn": DSN_WITH_PASSWORD}
    cycle["self"] = cycle

    configure_logging()
    get_logger("test").info("cyclic", payload=cycle)

    output = capsys.readouterr().out
    line = json.loads(output.strip().splitlines()[-1])

    assert line["event"] == "cyclic"
    assert "hunter2" not in output


def test_value_deeper_than_limit_is_not_printed() -> None:
    """За границей обхода значение не печатается: непроверенное могло бы вынести секрет."""
    deep = {"a": {"b": {"c": {"d": {"e": "хвост-структуры"}}}}}

    scrubbed = json.dumps(scrub_values(None, "info", {"payload": deep}), ensure_ascii=False)

    assert "хвост-структуры" not in scrubbed
    assert UNSCANNED in scrubbed


def test_large_collection_is_not_walked_whole() -> None:
    items = ["значение"] * (MAX_SCRUB_ITEMS + 5)

    scrubbed = scrub_values(None, "info", {"items": items})["items"]

    assert len(scrubbed) == MAX_SCRUB_ITEMS + 1
    assert "ещё 5" in scrubbed[-1]


def test_number_of_scanned_values_is_capped_per_record() -> None:
    """Ширина и глубина иначе перемножаются: лимит на коллекцию сам по себе не ограничивает
    обход. Процессор зовётся на каждой записи лога — стоимость обязана быть предсказуемой."""
    wide = {f"k{index}": ["значение"] * MAX_SCRUB_ITEMS for index in range(20)}

    scrubbed = json.dumps(scrub_values(None, "info", {"payload": wide}), ensure_ascii=False)

    assert scrubbed.count('"значение"') <= MAX_SCRUB_NODES


def test_db_password_from_query_string_is_scrubbed(local_env: pytest.MonkeyPatch) -> None:
    """`?password=…` регексп формы `user:pass@host` не ловит — пароль режется как значение."""
    local_env.setenv("DATABASE_URL", DSN_WITH_QUERY_PASSWORD)
    register_secret_values(Settings().scrubbable_secret_values())

    scrubbed = scrub_text(f"connection failed: {DSN_WITH_QUERY_PASSWORD}")

    assert "ПАРОЛЬ-БД" not in scrubbed
    # Диагностируемость: хост, порт и текст ошибки остаются.
    assert "db.internal:5432" in scrubbed
    assert "connection failed" in scrubbed


def test_redis_password_is_scrubbed_outside_url_form(local_env: pytest.MonkeyPatch) -> None:
    local_env.setenv("REDIS_URL", REDIS_URL_WITH_PASSWORD)
    register_secret_values(Settings().scrubbable_secret_values())

    scrubbed = scrub_text("auth failed, использован пароль ПАРОЛЬ-REDIS")

    assert "ПАРОЛЬ-REDIS" not in scrubbed
    assert "auth failed" in scrubbed


def test_registered_secret_never_appears_in_output(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(secret_values=["ОЧЕНЬ-СЕКРЕТНОЕ-ЗНАЧЕНИЕ"])
    get_logger("test").info("что-то пошло не так: ОЧЕНЬ-СЕКРЕТНОЕ-ЗНАЧЕНИЕ")

    assert "ОЧЕНЬ-СЕКРЕТНОЕ-ЗНАЧЕНИЕ" not in capsys.readouterr().out


async def test_lifespan_logs_presence_not_values(
    local_env: pytest.MonkeyPatch,
    make_app: Callable[[], FastAPI],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """lifespan не исполняется под ASGITransport, поэтому проверяется отдельно."""
    secret = "ЗНАЧЕНИЕ-КОТОРОГО-НЕ-ДОЛЖНО-БЫТЬ-В-ЛОГАХ"
    local_env.setenv("SECRET_KEY", secret)
    local_env.setenv("MASTER_KEY", "")
    local_env.setenv("DATABASE_URL", "postgresql+asyncpg://td:пароль-бд@127.0.0.1:1/td_test")

    from app.main import lifespan

    app = make_app()
    async with lifespan(app):
        pass

    output = capsys.readouterr().out
    started = next(json.loads(line) for line in output.splitlines() if '"app.started"' in line)

    assert secret not in output
    assert "пароль-бд" not in output
    # Имя секрета лежит значением, а не ключом: ключом его срезала бы цензура.
    assert "SECRET_KEY" in started["secrets"]["present"]
    assert "MASTER_KEY" in started["secrets"]["missing"]
    assert started["sentry"] == "disabled"


@pytest.mark.parametrize(
    "payload",
    [
        {DSN_WITH_PASSWORD},
        frozenset({DSN_WITH_PASSWORD}),
        DSN_WITH_PASSWORD.encode(),
        Connection(dsn=DSN_WITH_PASSWORD),
        RuntimeError(f"connection failed: {DSN_WITH_PASSWORD}"),
    ],
    ids=["set", "frozenset", "bytes", "object", "exception"],
)
def test_secret_in_non_container_value_is_scrubbed(
    payload: object, capsys: pytest.CaptureFixture[str]
) -> None:
    """Обход записи заходит только в dict/list/tuple, а всё прочее JSON-рендерер печатает
    через repr() — до этой точки такое значение уносило секрет нетронутым."""
    configure_logging()
    get_logger("test").info("probe", payload=payload)

    output = capsys.readouterr().out

    assert "hunter2" not in output
    # Диагностируемость: адрес остаётся, режется только пароль.
    assert "db.internal" in output


def test_exception_argument_does_not_leak_dsn(capsys: pytest.CaptureFixture[str]) -> None:
    """`log.error(..., error=exc)` — обычная строчка кода, а текст исключения штатно
    содержит DSN с паролем."""
    configure_logging()
    try:
        raise RuntimeError(f"connection failed: {DSN_WITH_PASSWORD}")
    except RuntimeError as exc:
        get_logger("test").error("db.connect_failed", error=exc)

    output = capsys.readouterr().out

    assert "hunter2" not in output
    assert "connection failed" in output


@pytest.mark.parametrize("key", ["code", "otp", "otp_code", "verification_code", "email"])
def test_auth_key_is_censored_at_any_depth(key: str, capsys: pytest.CaptureFixture[str]) -> None:
    """Auth логирует тело запроса: одноразовый код — секрет на время жизни, email —
    персональные данные. `password` и `token` на этой же глубине режутся давно."""
    value = f"значение-поля-{key}"

    configure_logging()
    get_logger("test").info("auth.request", request={"body": {key: value}})

    output = capsys.readouterr().out
    line = json.loads(output.strip().splitlines()[-1])

    assert value not in output
    assert line["request"]["body"][key] == REDACTED


def test_exc_info_survives_exhausted_walk_budget(capsys: pytest.CaptureFixture[str]) -> None:
    """При исчерпанном бюджете обход выродил бы кортеж `exc_info` в однокортеж. structlog
    его не распознаёт (len != 3), но считает истинным — и молча берёт окружающий
    sys.exc_info(). Вне except-блока это «NoneType: None» и потерянная трассировка."""
    try:
        raise RuntimeError(f"connection failed: {DSN_WITH_PASSWORD}")
    except RuntimeError:
        captured = sys.exc_info()

    wide = {f"k{index}": ["значение"] * MAX_SCRUB_ITEMS for index in range(20)}

    configure_logging()
    # Вызов снаружи except-блока: подменять трассировку окружением здесь нечем.
    get_logger("test").info("explicit", payload=wide, exc_info=captured)

    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])

    # Бюджет действительно исчерпан — иначе тест перестал бы проверять этот случай.
    # Ни одна коллекция здесь не шире MAX_SCRUB_ITEMS, значит остаток срезан бюджетом.
    assert "не проверено" in json.dumps(line["payload"], ensure_ascii=False)
    assert "RuntimeError: connection failed" in line["exception"]
    assert "hunter2" not in line["exception"]


def test_url_regex_is_not_run_on_text_without_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    """Регексп квадратичен по длине: строка word-символов на 1–4 КБ (JWT, base64, хеш)
    стоит миллисекунды на один прогон, а обход применяет его к сотням строк на запись."""
    seen: list[str] = []

    class CountingPattern:
        def sub(self, _replacement: str, text: str) -> str:
            seen.append(text)
            return text

    monkeypatch.setattr(logging_module, "_URL_CREDENTIALS", CountingPattern())

    assert scrub_text("a" * 4000) == "a" * 4000
    assert seen == []

    scrub_text(DSN_WITH_PASSWORD)

    assert len(seen) == 1


def teardown_module() -> None:
    """Возвращаем логгер в исходное состояние: configure_logging меняет глобальный root."""
    structlog.reset_defaults()
