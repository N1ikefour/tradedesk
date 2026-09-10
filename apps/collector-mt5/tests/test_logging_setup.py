"""Скраб лога. Инвариант: пароля счёта и сервисного токена в логах нет (CLAUDE.md §5).

Тесты нарочно кладут секрет туда, куда его никто не собирался класть, — под безобидным
именем поля и внутри чужого текста. Защита по имени поля такое пропустила бы, а
настоящая утечка выглядит именно так: пароль внутри текста исключения от чужой
библиотеки.

Здесь проверяется **механизм**: скраб, реестр, файл. Что пароль счёта в этот реестр
действительно попадает — вопрос проводки, и он проверяется в `test_worker.py`, где
подключение падает с паролем внутри текста ошибки. Разделение намеренное: тест, который
кладёт пароль в скраб руками, доказывает только то, что скраб умеет резать строки.
"""

from __future__ import annotations

from pathlib import Path

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


def test_there_is_one_log_file_and_the_spec_names_it() -> None:
    """С `X-66` процесс один — файлы на счёт больше не с кем делить (SPEC.md 8.2 п.3)."""
    assert logging_setup.LOG_NAME == "collector.log"


def test_setup_writes_a_scrubbed_line_to_the_file(tmp_path: Path) -> None:
    """Сквозная проверка: не «функция вернула словарь», а что в файле секрета нет.

    Секрет здесь только один — токен из `collector.env`, ровно то, что знает `main()` в
    момент подъёма логов. Пароль счёта в этот вызов не передаётся, потому что в бою его
    тогда ещё нет; что он попадает в скраб позже, проверяет `test_worker.py` на настоящей
    проводке — здесь такая проверка была бы самообманом.
    """
    log_file = tmp_path / "logs" / "account-test.log"
    logging_setup.setup_logging(log_file=log_file, level="INFO", secrets=(TOKEN,))
    logging_setup.get_logger("test").info("collector.probe", note=f"Bearer {TOKEN}", ok=True)
    written = log_file.read_text(encoding="utf-8")
    assert TOKEN not in written
    assert "collector.probe" in written
    assert logging_setup.SECRET_PLACEHOLDER in written


def test_a_secret_learned_after_startup_is_scrubbed_too(tmp_path: Path) -> None:
    """Реестр живой: скраб читает его на каждом событии, а не запоминает при старте.

    Без этого пароль счёта не попал бы в скраб никогда — он приходит из assignments уже
    после того, как логи подняты.
    """
    log_file = tmp_path / "logs" / "account-test.log"
    logging_setup.setup_logging(log_file=log_file, level="INFO", secrets=(TOKEN,))
    logging_setup.register_secret(PASSWORD)
    logging_setup.get_logger("test").info("collector.probe", note=f"вошли с {PASSWORD}")
    assert PASSWORD not in log_file.read_text(encoding="utf-8")


def test_a_short_value_is_not_taken_into_the_registry() -> None:
    logging_setup.register_secret("1234")
    assert "1234" not in logging_setup.known_secrets()
