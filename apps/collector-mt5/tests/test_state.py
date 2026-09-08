"""Единственное, что переживает перезапуск, — смещение часов брокера."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from collector import state


def test_offset_survives_a_restart(tmp_path: Path) -> None:
    """Без этого перезапуск в выходной означал бы простой до открытия рынка (SPEC.md 6.3)."""
    path = tmp_path / "collector-state.json"
    state.write_state(path, state.WorkerState(server_utc_offset_minutes=120))
    assert state.read_state(path).server_utc_offset_minutes == 120


def test_missing_file_means_unknown_not_a_crash(tmp_path: Path) -> None:
    assert state.read_state(tmp_path / "nope.json") == state.EMPTY


@pytest.mark.parametrize("text", ["", "{", "null", "[]", '{"server_utc_offset_minutes": "120"}'])
def test_broken_file_means_unknown_not_a_crash(text: str) -> None:
    """Файл — кэш. Испорченный он обязан давать «не знаю», а не отказ стартовать.

    Ошибка в другую сторону дороже: коллектор не поднимется на машине, до которой мы не
    дотянемся, и причину увидит только тот, кто откроет лог.
    """
    assert state.parse_state(text) == state.EMPTY


def test_true_is_not_read_as_one() -> None:
    """В Python `bool` наследует `int`, и `true` молча стал бы смещением в одну минуту."""
    assert state.parse_state('{"server_utc_offset_minutes": true}') == state.EMPTY


def test_write_is_atomic_enough_to_survive_a_power_cut(tmp_path: Path) -> None:
    """Запись идёт через временный файл: оборванная не портит прошлое значение."""
    path = tmp_path / "collector-state.json"
    state.write_state(path, state.WorkerState(server_utc_offset_minutes=120))
    state.write_state(path, state.WorkerState(server_utc_offset_minutes=180))
    assert state.read_state(path).server_utc_offset_minutes == 180
    assert list(tmp_path.glob("*.tmp")) == []


def test_state_file_lives_next_to_the_portable_terminal(tmp_path: Path) -> None:
    """Путь из MT5_PORTABLE_ROOT спека держит вне профиля пользователя (X-43)."""
    assert state.state_path(tmp_path / "acc").name == state.STATE_FILENAME


def test_no_secret_ever_reaches_the_file() -> None:
    """Пароль счёта живёт только в памяти процесса (CLAUDE.md §5)."""
    dumped = state.dump_state(state.WorkerState(server_utc_offset_minutes=120))
    assert set(json.loads(dumped)) == {"server_utc_offset_minutes"}
