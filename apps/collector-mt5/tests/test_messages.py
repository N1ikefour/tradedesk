"""Тексты, которые увидит человек, — SPEC.md 8.2.

Проверяется не «функция вернула строку», а три свойства, каждое из которых ломается
незаметно: сообщение доезжает до экрана целиком, оно на русском, и в нём нет ни пароля,
ни кода MT5 вместо объяснения.
"""

from __future__ import annotations

import inspect

import pytest

from collector import messages


def _text_constants() -> list[tuple[str, str]]:
    return [
        (name, value)
        for name, value in vars(messages).items()
        if name.isupper() and isinstance(value, str) and name not in {"ELLIPSIS"}
    ]


def test_every_message_survives_storage_intact() -> None:
    """`app/core/text.py` режет внешний текст до 200 символов при записи в счёт.

    Шаблон длиннее потолка означает, что человек увидит фразу, оборванную на полуслове,
    и не там, где решил автор.
    """
    for name, template in _text_constants():
        assert len(template) <= messages.MAX_MESSAGE_LENGTH, name


def test_messages_are_in_russian() -> None:
    """Сообщение, которое человек не прочтёт, — недоделанное сообщение (роль collector)."""
    for name, template in _text_constants():
        if name in {"ELLIPSIS"}:
            continue
        assert any("\u0400" <= char <= "\u04ff" for char in template), name


def test_fit_cuts_on_a_word_boundary() -> None:
    long_text = "слово " * 60
    fitted = messages.fit(long_text)
    assert len(fitted) <= messages.MAX_MESSAGE_LENGTH
    assert fitted.endswith(messages.ELLIPSIS)
    assert "  " not in fitted


def test_fit_keeps_short_text_as_is() -> None:
    assert messages.fit("  два   пробела  ") == "два пробела"


def test_a_closed_terminal_tells_the_human_to_open_it() -> None:
    """Главный отказ новой схемы (`X-66`): терминал открывает человек, а не коллектор.

    Все коды семейства «канал не работает» на шаге подключения означают для человека одно
    и то же действие, и различать их внутри семейства нечем: `-10005` наблюдался и на
    заведомо живом, доступном терминале.
    """
    for code in sorted(messages.LINK_FAILURES):
        text = messages.describe_mt5_failure(code, "IPC timeout", stage="connect")
        assert text == messages.TERMINAL_NOT_OPEN, code
        assert "пароль" not in text.casefold()


def test_the_same_link_failure_mid_work_promises_a_reconnect() -> None:
    """Посреди работы человеку делать нечего: коллектор переподключится сам."""
    for stage in ("history", "positions", "account_info"):
        text = messages.describe_mt5_failure(-10004, "IPC failed", stage=stage)
        assert text == messages.TERMINAL_LOST, stage


def test_no_message_asks_for_an_investor_password_any_more() -> None:
    """T-07: пароля в интерфейсе нет, и просить его — отправить человека искать несуществующее."""
    for name, template in _text_constants():
        assert "пароль инвестора" not in template.casefold(), name


def test_a_failed_authorization_sends_the_human_back_into_the_terminal() -> None:
    """Коллектор паролей не передаёт, поэтому −6 может значить только «вход не выполнен»."""
    text = messages.describe_mt5_failure(
        messages.RES_E_AUTH_FAILED, "Terminal: Authorization failed", stage="connect"
    )
    assert text == messages.NOT_AUTHORIZED
    assert "MetaTrader 5" in text


def test_the_numeric_code_is_not_pushed_onto_the_account_card() -> None:
    """X-67: код нужен в файле лога, а на карточке человеку нужен смысл."""
    text = messages.describe_mt5_failure(
        messages.RES_E_AUTO_TRADING_DISABLED, "Auto trading disabled", stage="connect"
    )
    assert "-8" not in text
    assert "автотрейдинг" in text.casefold()


@pytest.mark.parametrize(
    ("stage", "expected"),
    [("history", "историю сделок"), ("account_info", "не найдено")],
)
def test_the_same_code_means_different_things_on_different_steps(
    stage: messages.Stage, expected: str
) -> None:
    """-4 при запросе истории и -4 на других шагах — разные события, и текст различается."""
    text = messages.describe_mt5_failure(messages.RES_E_NOT_FOUND, "not found", stage=stage)
    assert expected in text


def test_unknown_code_carries_the_terminal_text_through() -> None:
    """Кода нет в таблице — человеку остаётся передать нам то, что сказал терминал."""
    text = messages.describe_mt5_failure(-424242, "Something new", stage="connect")
    assert "-424242" in text
    assert "Something new" in text


def test_unknown_code_with_an_empty_description_still_reads() -> None:
    text = messages.describe_mt5_failure(-424242, "", stage="positions")
    assert "пусто" in text


def test_describe_never_exceeds_the_storage_limit() -> None:
    """Текст терминала подставляется в шаблон, и длину его никто не обещал."""
    text = messages.describe_mt5_failure(-1, "x" * 5000, stage="connect")
    assert len(text) <= messages.MAX_MESSAGE_LENGTH


def test_not_windows_names_the_system() -> None:
    assert "Darwin" in messages.not_windows("Darwin")


def test_not_usd_names_the_currency() -> None:
    assert "EUR" in messages.not_usd("EUR")


def test_stage_literal_covers_every_call_site() -> None:
    """Страховка от опечатки в `stage`: перечень один и он закрытый."""
    signature = inspect.signature(messages.describe_mt5_failure)
    assert signature.parameters["stage"].kind is inspect.Parameter.KEYWORD_ONLY
