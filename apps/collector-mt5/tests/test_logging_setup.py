"""Скраб лога. Инвариант: сервисного токена в логах нет (CLAUDE.md §5).

Секрет у коллектора сегодня один — `COLLECTOR_TOKEN`: пароля счёта он не читает вовсе
(`T-07`). Тесты нарочно кладут секрет туда, куда его никто не собирался класть, — под
безобидным именем поля и внутри чужого текста. Защита по имени поля такое пропустила бы, а
настоящая утечка выглядит именно так: секрет внутри текста исключения от чужой библиотеки.

Проверяется здесь **механизм**: скраб, реестр, файл. Реестр остаётся живым не про запас, а
потому, что «секрет один» — состояние сегодняшнего дня, а не свойство конструкции.
"""

from __future__ import annotations

from pathlib import Path

from collector import logging_setup

TOKEN = "collector-token-0123456789"
# Секрет, о котором процесс узнаёт уже после подъёма логов. Своего такого у коллектора
# сейчас нет — им был пароль счёта из assignments, — но проверяется здесь механизм.
LATE_SECRET = "late-learned-secret-value"


def test_secret_under_an_innocent_field_name_is_still_cut() -> None:
    event = logging_setup.scrub_event({"note": f"ключ {LATE_SECRET}"}, [LATE_SECRET])
    assert LATE_SECRET not in event["note"]
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

    Токен из `collector.env` — ровно то, что знает `main()` в момент подъёма логов, и
    единственное, что коллектор обязан прятать сегодня.
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

    Секрет, узнанный после первой строки лога, обязан попадать под скраб без переделки
    проводки. Таким был пароль счёта из assignments, пока `T-07` не убрал его вовсе, — а
    свойство скраба пережило свой повод намеренно: следующий секрет придёт так же.
    """
    log_file = tmp_path / "logs" / "account-test.log"
    logging_setup.setup_logging(log_file=log_file, level="INFO", secrets=(TOKEN,))
    logging_setup.register_secret(LATE_SECRET)
    logging_setup.get_logger("test").info("collector.probe", note=f"ключ {LATE_SECRET}")
    assert LATE_SECRET not in log_file.read_text(encoding="utf-8")


def test_a_short_value_is_not_taken_into_the_registry() -> None:
    logging_setup.register_secret("1234")
    assert "1234" not in logging_setup.known_secrets()
