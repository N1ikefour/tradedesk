"""Подделки терминала и API. Настоящих здесь нет и быть не может.

`MetaTrader5` не существует под macOS, поэтому единственный способ проверить решения
коллектора — подставить вместо терминала объект с теми же методами. Всё, что подделка
не покрывает, названо в итоге задачи списком «требует Windows».
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from collector import logging_setup
from collector.api_client import Assignment, HeartbeatAccount, IngestResult
from collector.config import CollectorSettings
from collector.mt5_client import TerminalError

ACCOUNT_ID = "0192f1d4-2c6a-7c3f-9d1e-2b6a8f4c1d55"
COLLECTOR_ID = "test-machine"
TOKEN = "collector-token-0123456789"


@dataclass
class FakeDeal:
    """Строка `history_deals_get()`. Поля — ровно те, что читает `payload.py`."""

    ticket: int = 1
    order: int = 1
    time: int = 1_788_357_791
    time_msc: int = 1_788_357_791_000
    type: int = 0
    entry: int = 0
    magic: int = 0
    position_id: int = 100
    reason: int = 3
    volume: float = 0.1
    price: float = 1.08543
    commission: float = -0.35
    swap: float = 0.0
    profit: float = 0.0
    fee: float = 0.0
    symbol: str = "EURUSD"
    comment: str = "MarketBuy"


@dataclass
class FakePosition:
    """Строка `positions_get()`: идентификатор позиции лежит в `identifier`."""

    identifier: int = 100
    symbol: str = "XAUUSD"
    type: int = 0
    volume: float = 0.5
    price_open: float = 2410.1
    time: int = 1_788_357_000
    sl: float = 2400.0
    tp: float = 2450.0
    profit: float = 12.3


@dataclass
class FakeAccountInfo:
    currency: str = "USD"
    margin_mode: int = 2
    balance: float = 10_000.0
    equity: float = 10_012.5


@dataclass
class FakeTerminal:
    """Терминал, который делает ровно то, что ему сказали в тесте."""

    deals: list[FakeDeal] = field(default_factory=list)
    positions: list[FakePosition] = field(default_factory=list)
    info: FakeAccountInfo = field(default_factory=FakeAccountInfo)
    tick_time: int | None = None
    # Живой рынок обновляет котировку между опросами, и на этом стоит подтверждение
    # смещения (`sync.resolve_offset`). `tick_step=0` — застывшая котировка: рынок
    # закрыт, инструмент не торгуется, терминал отдаёт один и тот же тик.
    tick_step: int = 60
    connect_errors: list[TerminalError] = field(default_factory=list)
    connected: int = 0
    closed: int = 0
    history_calls: list[tuple[datetime, datetime]] = field(default_factory=list)
    ticks_asked: int = 0

    def connect(self) -> None:
        self.connected += 1
        if self.connect_errors:
            raise self.connect_errors.pop(0)

    def wait_for_history(self) -> None:
        return None

    def account_info(self) -> FakeAccountInfo:
        return self.info

    def history_deals(self, start: datetime, end: datetime) -> Sequence[FakeDeal]:
        self.history_calls.append((start, end))
        return list(self.deals)

    def open_positions(self) -> Sequence[FakePosition]:
        return list(self.positions)

    def server_time(self) -> int | None:
        if self.tick_time is None:
            return None
        moment = self.tick_time + self.tick_step * self.ticks_asked
        self.ticks_asked += 1
        return moment

    def close(self) -> None:
        self.closed += 1


@dataclass
class FakeApi:
    """API без сети. Помнит всё, что ему отправили."""

    assignment: Assignment | None = None
    batches: list[dict[str, Any]] = field(default_factory=list)
    heartbeats: list[HeartbeatAccount] = field(default_factory=list)
    refuse: Exception | None = None

    def assignments(self, collector_id: str) -> list[Assignment]:
        return [self.assignment] if self.assignment is not None else []

    def send_deals(self, batch: dict[str, Any]) -> IngestResult:
        if self.refuse is not None:
            raise self.refuse
        self.batches.append(batch)
        deals = batch["deals"]
        return IngestResult(
            received=len(deals),
            inserted=len(deals),
            duplicates=0,
            positions_rebuilt=0,
            sync_run_id="0192f1d4-2c6a-7c3f-9d1e-000000000001",
        )

    def heartbeat(self, collector_id: str, accounts: Iterable[HeartbeatAccount]) -> None:
        self.heartbeats.extend(accounts)


@pytest.fixture(autouse=True)
def _no_secrets_between_tests() -> Iterator[None]:
    """Реестр секретов скраба — состояние процесса, а тесты его наполняют.

    Конструктор `Assignment` вносит пароль в скраб (это и есть механизм из `CLAUDE.md` §5),
    поэтому без уборки один тест влиял бы на вывод другого.
    """
    logging_setup.forget_secrets()
    yield
    logging_setup.forget_secrets()


@pytest.fixture
def settings(tmp_path: Any) -> CollectorSettings:
    return CollectorSettings(
        api_url="http://localhost:8000",
        collector_token=TOKEN,  # type: ignore[arg-type]
        collector_id=COLLECTOR_ID,
        mt5_terminal_exe=tmp_path / "terminal64.exe",
        mt5_portable_root=tmp_path / "td-terminals",
        sync_interval_seconds=60,
        heartbeat_interval_seconds=60,
        first_sync_days=3650,
        max_accounts=3,
        log_level="INFO",
        log_dir=tmp_path / "logs",
    )


@pytest.fixture
def assignment() -> Assignment:
    return Assignment(
        account_id=ACCOUNT_ID,
        server="E-Global-Real",
        login=1234567,
        password="investor-secret",
        sync_requested_at=None,
        last_sync_at=None,
        status="pending",
    )


def moment(**shift: float) -> datetime:
    """Опорный момент тестов: 2 сентября 2026, 14:03:11 UTC, плюс сдвиг."""
    return datetime(2026, 9, 2, 14, 3, 11, tzinfo=UTC) + timedelta(**shift)


def deal(ticket: int = 1, at: int = 1_788_357_791, **overrides: Any) -> FakeDeal:
    """Сделка с согласованными `time` и `time_msc`.

    Граница сверяет их между собой и отвергает батч целиком при расхождении, поэтому
    случайно разъехавшаяся подделка молча выпала бы из батча, а тест увидел бы пустоту
    вместо ошибки.
    """
    return FakeDeal(ticket=ticket, time=at, time_msc=at * 1000, **overrides)
