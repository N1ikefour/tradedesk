"""Валидация тел и чистая логика домена счетов (S1-06).

Здесь то, что не требует ни базы, ни приложения: правила полей, связка «платформа →
обязательные поля», решение «сбрасывать ли статус» и то, что синк делает с карточкой
счёта. Живые маршруты — в `tests/integration/test_accounts.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domains.accounts import models, service
from app.domains.accounts.schemas import (
    LABEL_MAX_LENGTH,
    PASSWORD_MAX_LENGTH,
    AccountCreateRequest,
    AccountUpdateRequest,
)

MT5: dict[str, Any] = {
    "label": "Демо FTMO",
    "platform": "mt5",
    "server": "FTMO-Demo",
    "login": 5001234,
    "password": "investor-pass",
}


def create(**overrides: Any) -> AccountCreateRequest:
    return AccountCreateRequest(**{**MT5, **overrides})


def fields(error: ValidationError) -> set[str]:
    return {".".join(str(part) for part in item["loc"]) for item in error.errors()}


def account(**overrides: Any) -> models.TradingAccount:
    values: dict[str, Any] = {
        "id": uuid4(),
        "user_id": uuid4(),
        "label": "Демо FTMO",
        "is_demo": True,
        "color": "#2563eb",
        "platform": "mt5",
        "broker": None,
        "server": "FTMO-Demo",
        "login": 5001234,
        "currency": "USD",
        "account_type": None,
        "server_utc_offset_minutes": None,
        "status": service.STATUS_PENDING,
        "status_message": None,
        "sync_requested_at": None,
        "last_sync_at": None,
        "last_heartbeat_at": None,
        "collector_id": None,
        "sort_order": 0,
        "created_at": datetime(2026, 9, 1, tzinfo=UTC),
    }
    return models.TradingAccount(**{**values, **overrides})


# --- связка «платформа → поля» -----------------------------------------------


def test_mt5_requires_server_login_and_password() -> None:
    for missing in ("server", "login", "password"):
        with pytest.raises(ValidationError) as raised:
            create(**{missing: None})
        assert "MT5" in str(raised.value), missing


@pytest.mark.parametrize("platform", ["manual", "csv"])
@pytest.mark.parametrize("extra", ["server", "login", "password"])
def test_non_mt5_rejects_mt5_fields(platform: str, extra: str) -> None:
    """Пароль у ручного счёта некуда девать: коллектор в него не ходит."""
    body = {"label": "Ручной", "platform": platform, extra: MT5[extra]}

    with pytest.raises(ValidationError):
        AccountCreateRequest(**body)


def test_manual_account_needs_only_a_label() -> None:
    request = AccountCreateRequest(label="Ручной", platform="manual")

    assert request.server is None
    assert request.password is None
    assert request.is_demo is False
    assert request.color is None


# --- поля --------------------------------------------------------------------


@pytest.mark.parametrize("raw", ["", "   ", "\n\t"])
def test_blank_label_is_rejected(raw: str) -> None:
    with pytest.raises(ValidationError) as raised:
        create(label=raw)

    assert fields(raised.value) == {"label"}


def test_label_is_trimmed() -> None:
    assert create(label="  Демо  ").label == "Демо"


def test_too_long_label_is_rejected() -> None:
    with pytest.raises(ValidationError):
        create(label="я" * (LABEL_MAX_LENGTH + 1))


def test_control_characters_are_rejected_in_text_fields() -> None:
    """Строка уезжает в UI и в логи: перевод строки там — заготовка под инъекцию."""
    for field, value in (("label", "Демо\nFTMO"), ("server", "FTMO\rDemo"), ("broker", "A\x00B")):
        with pytest.raises(ValidationError) as raised:
            create(**{field: value})
        assert fields(raised.value) == {field}


def test_blank_broker_becomes_null() -> None:
    assert create(broker="   ").broker is None
    assert create(broker=None).broker is None


@pytest.mark.parametrize("raw", [0, -1, True])
def test_bad_login_is_rejected(raw: object) -> None:
    """`True` — не «логин 1»: bool наследует int, и без явного отказа он прошёл бы молча."""
    with pytest.raises(ValidationError) as raised:
        create(login=raw)

    assert fields(raised.value) == {"login"}


def test_unknown_color_is_rejected() -> None:
    with pytest.raises(ValidationError):
        create(color="#123456")


def test_unknown_field_is_rejected() -> None:
    """Опечатка в имени поля иначе выглядит как «сохранено», а изменилось ничего."""
    with pytest.raises(ValidationError):
        create(colour="#2563eb")


@pytest.mark.parametrize("raw", ["", "x" * (PASSWORD_MAX_LENGTH + 1), "pass\nword"])
def test_bad_password_is_rejected(raw: str) -> None:
    with pytest.raises(ValidationError) as raised:
        create(password=raw)

    assert fields(raised.value) == {"password"}


def test_password_spaces_are_significant() -> None:
    """Пароль не подрезается: пробел по краям — часть пароля, а не форматирование."""
    password = create(password=" a b ").password

    assert password is not None
    assert password.get_secret_value() == " a b "


def test_password_is_not_printed_by_repr() -> None:
    """`repr` модели уезжает и в traceback, и в лог: SecretStr закрывает этот путь."""
    request = create(password="investor-pass")

    assert "investor-pass" not in repr(request)
    assert "investor-pass" not in str(request.password)


# --- частичная правка --------------------------------------------------------


def test_patch_distinguishes_missing_from_null() -> None:
    assert AccountUpdateRequest().model_dump(exclude_unset=True) == {}
    assert AccountUpdateRequest(broker=None).model_dump(exclude_unset=True) == {"broker": None}


@pytest.mark.parametrize("field", ["label", "is_demo", "color", "server", "password"])
def test_patch_rejects_null_where_there_is_nothing_to_clear(field: str) -> None:
    with pytest.raises(ValidationError) as raised:
        AccountUpdateRequest(**{field: None})

    assert fields(raised.value) == {field}


# --- сброс статуса при правке ------------------------------------------------


def test_password_always_resets_the_connection() -> None:
    """Пароль набирают заново только потому, что старый не подошёл."""
    assert service._resets_connection(account(), {"password": "x"}) is True


def test_unchanged_server_and_login_do_not_reset_the_connection() -> None:
    """Ключевой случай развилки: форма редактирования шлёт карточку целиком.

    Если бы решало присутствие поля, переименование счёта роняло бы работающий синк
    в `pending` — и `S1-11` получил бы «синхронизация остановилась» на каждой правке.
    """
    changes = {"label": "Новое имя", "server": "FTMO-Demo", "login": 5001234, "color": "#16a34a"}

    assert service._resets_connection(account(), changes) is False


@pytest.mark.parametrize(
    "changes", [{"server": "FTMO-Real"}, {"login": 9}, {"server": "FTMO-Real", "login": 9}]
)
def test_changed_identity_resets_the_connection(changes: dict[str, Any]) -> None:
    assert service._resets_connection(account(), changes) is True


def test_cosmetic_changes_never_reset_the_connection() -> None:
    changes = {"label": "Новое", "is_demo": False, "color": "#dc2626", "sort_order": 3}

    assert service._resets_connection(account(), changes) is False


# --- коллектор на связи ------------------------------------------------------

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)


def test_account_without_a_heartbeat_is_offline() -> None:
    """Ни разу не выходивший на связь коллектор — не «онлайн по умолчанию».

    Ответ `sync-now` иначе обещал бы скорый синк на счёте, к которому вообще никто
    не подключался: ровно то состояние, в котором пользователь и жмёт кнопку.
    """
    assert service.is_collector_online(account(), now=NOW) is False


@pytest.mark.parametrize(
    ("age", "online"),
    [
        (timedelta(seconds=0), True),
        (timedelta(minutes=4, seconds=59), True),
        (service.COLLECTOR_OFFLINE_AFTER, True),
        (service.COLLECTOR_OFFLINE_AFTER + timedelta(seconds=1), False),
        (timedelta(days=1), False),
    ],
)
def test_heartbeat_age_decides_online(age: timedelta, online: bool) -> None:
    """Граница ровно на пороге SPEC.md 9.3 и 10: пять минут — ещё на связи."""
    row = account(last_heartbeat_at=NOW - age)

    assert service.is_collector_online(row, now=NOW) is online


# --- валюта ------------------------------------------------------------------


@pytest.mark.parametrize("currency", [None, "USD", "usd", " USD "])
def test_supported_currency_has_no_message(currency: str | None) -> None:
    assert service.unsupported_currency_message(currency) is None


def test_unsupported_currency_names_itself() -> None:
    message = service.unsupported_currency_message("EUR")

    assert message is not None
    assert "EUR" in message
    assert "USD" in message


def test_currency_code_from_the_terminal_is_sanitised() -> None:
    """Код валюты приходит извне и попадает в текст для пользователя.

    Сообщение об ошибке — не место для произвольной строки чужого происхождения:
    длина ограничена, всё кроме букв и цифр вырезано.
    """
    message = service.unsupported_currency_message("<script>alert(1)</script>")

    assert message is not None
    assert "<" not in message and ">" not in message
    assert "ALERT" in message


# --- что синк делает с карточкой ---------------------------------------------


def test_sync_marks_the_account_connected() -> None:
    row = account(status=service.STATUS_NEEDS_ATTENTION, status_message="Неверный пароль")
    moment = datetime(2026, 9, 2, 14, 3, tzinfo=UTC)

    service.apply_sync_result(
        row,
        currency="USD",
        margin_mode="hedging",
        server_utc_offset_minutes=180,
        synced_at=moment,
    )

    assert row.status == service.STATUS_CONNECTED
    assert row.status_message is None
    assert row.account_type == "hedging"
    assert row.server_utc_offset_minutes == 180
    assert row.last_sync_at == moment


def test_non_usd_account_needs_attention_instead_of_connected() -> None:
    """DoD S1-06: не-USD в `account_info` → `needs_attention` с сообщением.

    Проверка живёт рядом с выставлением `connected` намеренно (см. `apply_sync_result`):
    молча принятая валюта не имеет ни одного внешнего признака — суммы просто неверны.
    """
    row = account(status=service.STATUS_CONNECTED)

    service.apply_sync_result(row, currency="EUR", margin_mode="netting")

    assert row.status == service.STATUS_NEEDS_ATTENTION
    assert row.status_message is not None
    assert "EUR" in row.status_message
    # Валюта в БД не переписывается: колонка закрыта check (currency = 'USD').
    assert row.currency == "USD"
    # Остальное синк всё равно применил: сделки-то пришли.
    assert row.account_type == "netting"


def test_sync_does_not_resume_a_paused_account() -> None:
    """Пауза — решение пользователя; батч, пришедший следом, её не отменяет."""
    row = account(status=service.STATUS_PAUSED)

    service.apply_sync_result(row, currency="USD")

    assert row.status == service.STATUS_PAUSED
    assert row.last_sync_at is not None


def test_sync_without_account_info_keeps_the_status_moving() -> None:
    """`account_info` необязателен (SPEC.md 5.3): без него счёт всё равно подключён."""
    row = account()

    service.apply_sync_result(row)

    assert row.status == service.STATUS_CONNECTED
    assert row.account_type is None
    assert row.last_sync_at is not None
    assert datetime.now(UTC) - row.last_sync_at < timedelta(seconds=10)


def test_unknown_margin_mode_is_ignored() -> None:
    """`account_type` закрыт check-ограничением: мусор из терминала не должен ронять батч."""
    row = account(account_type="hedging")

    service.apply_sync_result(row, margin_mode="что-то новое")

    assert row.account_type == "hedging"
