"""Скраб лога. Инвариант: пароля счёта и сервисного токена в логах нет (CLAUDE.md §5).

Тесты нарочно кладут секрет туда, куда его никто не собирался класть, — под безобидным
именем поля и внутри чужого текста. Защита по имени поля такое пропустила бы, а
настоящая утечка выглядит именно так: пароль внутри текста исключения от чужой
библиотеки.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from collector import logging_setup

TOKEN = "collector-token-0123456789"
PASSWORD = "investor-secret-pass"


def test_secret_under_an_innocent_field_name_is_still_cut() -> None:
    event = logging_setup.scrub_event({"note": f"вошли с {PASSWORD}"}, [PASSWORD])
    assert PASSWORD not in event["note"]
    assert logging_setup.SECRET_PLACEHOLDER in event["note"]


def test_secret_inside_a_nested_structure_is_cut() -> None:
    event = logging_setup.scrub_event(
        {"batch": {"headers": [f"Bearer {TOKEN}"]}, "count": 5}, [TOKEN]
    )
    assert TOKEN not in str(event)
    assert event["count"] == 5


def test_scrub_survives_values_that_are_not_text() -> None:
    event = logging_setup.scrub_event({"n": 1, "f": 1.5, "b": None, "t": (1, 2)}, [TOKEN])
    assert event == {"n": 1, "f": 1.5, "b": None, "t": (1, 2)}


def test_short_strings_are_not_treated_as_secrets() -> None:
    """Иначе двухсимвольная подстрока превратила бы весь лог в решето из звёздочек."""
    event = logging_setup.scrub_event({"note": "abc EURUSD"}, ["ab"])
    assert event["note"] == "abc EURUSD"


def test_nothing_to_scrub_leaves_the_event_alone() -> None:
    original = {"note": "всё хорошо"}
    assert logging_setup.scrub_event(original, []) == original


def test_log_file_is_per_account() -> None:
    """S1-09 поднимет процесс на счёт, а RotatingFileHandler между процессами не дружит."""
    name = logging_setup.account_log_name("0192f1d4-2c6a-7c3f-9d1e-2b6a8f4c1d55")
    assert name == "account-0192f1d4-2c6a-7c3f-9d1e-2b6a8f4c1d55.log"


@pytest.mark.parametrize("account_id", ["../../etc/passwd", "a\\b", ""])
def test_log_name_never_leaves_the_folder(account_id: str) -> None:
    name = logging_setup.account_log_name(account_id)
    assert "/" not in name
    assert "\\" not in name
    assert ".." not in name


def test_setup_writes_a_scrubbed_line_to_the_file(tmp_path: Path) -> None:
    """Сквозная проверка: не «функция вернула словарь», а что в файле секрета нет."""
    log_file = tmp_path / "logs" / "account-test.log"
    logging_setup.setup_logging(log_file=log_file, level="INFO", secrets=(TOKEN, PASSWORD))
    logging_setup.get_logger("test").info("collector.probe", note=f"Bearer {TOKEN}", ok=True)
    written = log_file.read_text(encoding="utf-8")
    assert TOKEN not in written
    assert "collector.probe" in written
    assert logging_setup.SECRET_PLACEHOLDER in written
