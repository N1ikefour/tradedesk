"""Замена RUF001 для коллектора — и она сильнее.

Прежде гомоглиф в тикере ловил линтер: правило RUF001 было включено в `pyproject.toml`
именно с этим обоснованием. На деле оно срабатывало исключительно на русском тексте
сообщений (31 раз) и ни разу — на символе, потому что символьных литералов в коллекторе
всего два. В `S1-08` правило выключено, а гарантия перенесена сюда: проверяются сами
константы, а не форма исходника, и проверка не зависит от эвристики «похоже ли слово на
латинское».

Список констант **не заведён руками** — он собирается рефлексией по модулям. Руками
собранный список покрывает то, что было в день его написания, и молча пропускает
константу, добавленную завтра: ровно тот класс дыры, от которого этот файл и охраняет.
Исключён один модуль — `messages`: там текст для человека, и он по требованию `SPEC.md`
§8.2 русский. Всё остальное в коллекторе — имена инструментов, значения перечислений
контракта, ключи файлов и форматы, и латиница в них не стилистика, а условие работы.

Кириллическая «Е» в `EURUSD` из `TIME_PROBE_SYMBOLS` означала бы, что смещение часов
брокера не определяется никогда: `symbol_info_tick` вернёт `None` по несуществующему
инструменту, батч не уедет, а в логе будет «свежей котировки нет» — то есть симптом,
уводящий в сторону от причины (`docs/mt5-assumptions.md`, допущение 17).
"""

from __future__ import annotations

from types import ModuleType
from typing import Any

import pytest

from collector import (
    api_client,
    config,
    logging_setup,
    messages,
    mt5_client,
    payload,
    state,
    sync,
    worker,
)

# Модули, у которых строковые константы — машинные значения. `messages` сюда не входит
# намеренно и единственный: его константы читает человек.
ASCII_MODULES: tuple[ModuleType, ...] = (
    api_client,
    config,
    logging_setup,
    mt5_client,
    payload,
    state,
    sync,
    worker,
)


# Тексты для человека, где кириллица обязательна. Исключаются по значению, а не по имени
# модуля: сообщение, разложенное по таблице в `worker.py`, остаётся тем же сообщением.
HUMAN_TEXTS = frozenset(value for value in vars(messages).values() if isinstance(value, str))


def _strings(value: Any) -> list[str]:
    """Все строки внутри значения константы, на любой глубине вложенности."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, (tuple, list, set, frozenset)):
        return [text for item in value for text in _strings(item)]
    if isinstance(value, dict):
        return [text for item in (*value.keys(), *value.values()) for text in _strings(item)]
    return []


def _constants() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for module in ASCII_MODULES:
        for name, value in vars(module).items():
            if not name.isupper() or name.startswith("_"):
                continue
            found.extend(
                (f"{module.__name__}.{name}", text)
                for text in _strings(value)
                if text not in HUMAN_TEXTS
            )
    return found


CONSTANTS = _constants()


def test_reflection_actually_found_the_constants() -> None:
    """Страховка на саму страховку: опечатка в обходе дала бы пустой список и зелёный тест."""
    names = {name for name, _ in CONSTANTS}
    assert "collector.mt5_client.TIME_PROBE_SYMBOLS" in names
    assert "collector.payload.MARGIN_MODES" in names
    assert "collector.worker.USD" in names
    assert len(CONSTANTS) >= 20


@pytest.mark.parametrize(("name", "value"), CONSTANTS, ids=[name for name, _ in CONSTANTS])
def test_machine_constants_are_ascii(name: str, value: str) -> None:
    assert value.isascii(), name


def test_time_probes_are_liquid_instruments_not_placeholders() -> None:
    """Смысл списка — свежесть котировки: чем ликвиднее инструмент, тем меньше её возраст."""
    assert "EURUSD" in mt5_client.TIME_PROBE_SYMBOLS
    assert len(set(mt5_client.TIME_PROBE_SYMBOLS)) == len(mt5_client.TIME_PROBE_SYMBOLS)
    for symbol in mt5_client.TIME_PROBE_SYMBOLS:
        assert symbol == symbol.strip() != ""
