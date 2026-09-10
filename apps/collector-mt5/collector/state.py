"""Единственное, что коллектор помнит между запусками, — смещение часов брокера.

Всё остальное состояние синхронизации живёт на сервере: `last_sync_at` приходит в
assignments, дубли снимает ингест. Смещение — исключение, и вот почему. Взять его можно
только из свежей котировки (`SPEC.md` §6.3), а котировок нет, пока рынок закрыт. Без
записи на диск перезапуск коллектора в субботу означал бы, что до понедельника он не
может отправить ни одного батча: смещение обязательно в каждом.

Файл — на счёт, и лежит он в `STATE_DIR` рядом с логами. До `X-66` его местом была папка
портабельной копии терминала (`MT5_PORTABLE_ROOT\\<account_id>`); копий больше нет —
терминал открывает человек, — а смещение у каждого брокера своё, поэтому один общий файл
на все счета сложил бы разные смещения в одно значение.

Секретов в файле нет и быть не может: пароль счёта коллектору больше не нужен вовсе
(`T-07`), а токен установки сюда не попадает ни при какой ошибке.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

OFFSET_KEY: Final = "server_utc_offset_minutes"


@dataclass(frozen=True)
class WorkerState:
    """Что коллектор знает о брокере этого счёта на момент старта."""

    server_utc_offset_minutes: int | None = None


EMPTY: Final = WorkerState()


def parse_state(text: str) -> WorkerState:
    """Разбор файла состояния. Любой мусор — пустое состояние, а не исключение.

    Файл — кэш, а не источник правды: испорченный или дописанный до половины (машину
    выключили посреди записи) он обязан приводить к «смещение неизвестно», а не к отказу
    стартовать. Цена ошибки в другую сторону слишком велика — коллектор не поднимется на
    машине, до которой мы не дотянемся.
    """
    try:
        data: Any = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return EMPTY
    if not isinstance(data, dict):
        return EMPTY
    offset = data.get(OFFSET_KEY)
    if not isinstance(offset, int) or isinstance(offset, bool):
        return EMPTY
    return WorkerState(server_utc_offset_minutes=offset)


def dump_state(state: WorkerState) -> str:
    return json.dumps({OFFSET_KEY: state.server_utc_offset_minutes}, ensure_ascii=False)


def state_file_name(account_id: str) -> str:
    """Имя файла состояния счёта. Идентификатор — UUID, посторонних символов в нём нет."""
    safe = "".join(char for char in account_id if char.isalnum() or char in "-_")
    return f"offset-{safe or 'unknown'}.json"


def state_path(state_dir: Path, account_id: str) -> Path:
    return state_dir / state_file_name(account_id)


def read_state(path: Path) -> WorkerState:
    try:
        return parse_state(path.read_text(encoding="utf-8"))
    except OSError:
        return EMPTY


def write_state(path: Path, state: WorkerState) -> None:
    """Запись через временный файл: оборванная запись не портит прошлое значение."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(dump_state(state), encoding="utf-8")
    temporary.replace(path)
