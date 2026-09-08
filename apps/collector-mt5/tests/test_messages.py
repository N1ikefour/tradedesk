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


def test_wrong_investor_password_says_so_in_words() -> None:
    """S1-10 DoD: неверный пароль виден в UI как «Неверный пароль инвестора»."""
    text = messages.describe_mt5_failure(
        messages.RES_E_AUTH_FAILED,
        "Terminal: Authorization failed",
        stage="connect",
        server="E-Global-Real",
        login=1234567,
    )
    assert text.startswith("Неверный пароль инвестора")
    assert "E-Global-Real" in text
    assert "1234567" in text


def test_unknown_server_is_told_apart_when_the_terminal_says_so() -> None:
    """Единственная ветка, отличающая имя сервера от пароля, — по тексту терминала.

    ⚠️ Сам текст не наблюдался: терминала на машине разработки нет. Тест фиксирует
    поведение ветки, а не факт, что брокер отвечает именно так.
    """
    text = messages.describe_mt5_failure(
        messages.RES_E_AUTH_FAILED,
        "Terminal: server not found",
        stage="connect",
        server="Nonexistent-Server",
    )
    assert text.startswith("Сервер брокера")
    assert "Nonexistent-Server" in text


def test_terminal_that_does_not_start_names_the_path() -> None:
    text = messages.describe_mt5_failure(
        messages.RES_E_INTERNAL_FAIL_INIT,
        "IPC initialize failed",
        stage="connect",
        terminal_path="C:\\td-terminals\\acc\\terminal64.exe",
    )
    assert "не запускается" in text
    assert "C:\\td-terminals\\acc\\terminal64.exe" in text


def test_timeout_is_not_confused_with_a_wrong_password() -> None:
    text = messages.describe_mt5_failure(
        messages.RES_E_INTERNAL_FAIL_TIMEOUT, "IPC timeout", stage="connect"
    )
    assert "не ответил вовремя" in text
    assert "пароль" not in text.casefold()


@pytest.mark.parametrize(
    ("stage", "expected"),
    [("history", "историю сделок"), ("account_info", "не нашёл счёт")],
)
def test_the_same_code_means_different_things_on_different_steps(
    stage: messages.Stage, expected: str
) -> None:
    """-4 при запросе истории и -4 при входе — разные события, и текст обязан различаться."""
    text = messages.describe_mt5_failure(
        messages.RES_E_NOT_FOUND, "not found", stage=stage, server="S", login=1
    )
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
