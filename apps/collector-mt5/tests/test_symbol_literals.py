"""Замена RUF001 для коллектора — и она сильнее.

Прежде гомоглиф в тикере ловил линтер: правило RUF001 было включено в `pyproject.toml`
именно с этим обоснованием. На деле оно срабатывало исключительно на русском тексте
сообщений (31 раз) и ни разу — на символе, потому что символьных литералов в коллекторе
всего два. В `S1-08` правило выключено, а гарантия перенесена сюда: проверяются сами
константы, а не форма исходника, и проверка не зависит от эвристики «похоже ли слово на
латинское».

Кириллическая «Е» в `EURUSD` из `TIME_PROBE_SYMBOLS` означала бы, что смещение часов
брокера не определяется никогда: `symbol_info_tick` вернёт `None` по несуществующему
инструменту, батч не уедет, а в логе будет «свежей котировки нет» — то есть симптом,
уводящий в сторону от причины (`docs/mt5-assumptions.md`, допущение 17).
"""

from __future__ import annotations

import pytest

from collector import mt5_client, payload, worker

SYMBOL_CONSTANTS: list[tuple[str, str]] = [
    *(
        (f"TIME_PROBE_SYMBOLS[{index}]", value)
        for index, value in enumerate(mt5_client.TIME_PROBE_SYMBOLS)
    ),
    ("worker.USD", worker.USD),
    ("payload.SOURCE_COLLECTOR", payload.SOURCE_COLLECTOR),
    *((f"MARGIN_MODES[{code}]", name) for code, name in payload.MARGIN_MODES.items()),
]


@pytest.mark.parametrize(("name", "value"), SYMBOL_CONSTANTS)
def test_symbol_constants_are_ascii(name: str, value: str) -> None:
    assert value.isascii(), name
    assert value == value.strip()
    assert value != ""


def test_time_probes_are_liquid_instruments_not_placeholders() -> None:
    """Смысл списка — свежесть котировки: чем ликвиднее инструмент, тем меньше её возраст."""
    assert "EURUSD" in mt5_client.TIME_PROBE_SYMBOLS
    assert len(set(mt5_client.TIME_PROBE_SYMBOLS)) == len(mt5_client.TIME_PROBE_SYMBOLS)
