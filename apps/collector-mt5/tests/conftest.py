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
OTHER_ACCOUNT_ID = "0192f1d4-2c6a-7c3f-9d1e-2b6a8f4c1d66"
COLLECTOR_ID = "test-machine"
TOKEN = "collector-token-0123456789"
LOGIN = 1234567
SERVER = "E-Global-Real"


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
    """`account_info()`. `login` и `server` здесь потому, что ими опознают счёт (X-66)."""

    login: int = LOGIN
    server: str = SERVER
    currency: str = "USD"
    margin_mode: int = 2
    balance: float = 10_000.0
    equity: float = 10_012.5


def garbled_account_info(login: Any = "1234567") -> FakeAccountInfo:
    """`account_info()`, нарушивший собственное обещание: номер счёта пришёл не числом.

    Библиотека объявляет `login` целым (`payload.RawAccountInfo`), и проверить это обещание
    на машине разработки нечем. Ложь проходит мимо типов через `Any` — ровно так же, как
    прошла бы мимо них ложь настоящего терминала: аннотация ничего не проверяет в рантайме.
    """
    return FakeAccountInfo(login=login)


@dataclass
class FakeTerminal:
    """Терминал, который делает ровно то, что ему сказали в тесте."""

    deals: list[FakeDeal] = field(default_factory=list)
    positions: list[FakePosition] = field(default_factory=list)
    info: FakeAccountInfo = field(default_factory=FakeAccountInfo)
    # Чем ответит `account_info()` после `switch_after` вызовов. Так проверяется сторож
    # `X-66`: человек переключил счёт, пока терминал отдавал историю.
    info_after: FakeAccountInfo | None = None
    switch_after: int = 1
    # Второй способ переключить счёт: не «после N вызовов `account_info()`», а **внутри**
    # `history_deals()`. Разница в том, что закрепляется: со `switch_after` подделка
    # переключается сама по себе, и сторож увидел бы чужой счёт, где бы он ни стоял. Здесь
    # переключение — следствие чтения истории, поэтому сторож, переставленный до неё,
    # спросит терминал слишком рано, получит прежний счёт и отправит чужой батч.
    switch_during_history: bool = False
    tick_time: int | None = None
    # Живой рынок обновляет котировку между опросами, и на этом стоит подтверждение
    # смещения (`sync.resolve_offset`). `tick_step=0` — застывшая котировка: рынок
    # закрыт, инструмент не торгуется, терминал отдаёт один и тот же тик.
    tick_step: int = 60
    connect_errors: list[TerminalError] = field(default_factory=list)
    info_errors: list[TerminalError] = field(default_factory=list)
    history_errors: list[TerminalError] = field(default_factory=list)
    connected: int = 0
    closed: int = 0
    history_calls: list[tuple[datetime, datetime]] = field(default_factory=list)
    ticks_asked: int = 0
    info_calls: int = 0
    waited: int = 0
    switched_in_history: bool = field(default=False, init=False)

    def connect(self) -> None:
        self.connected += 1
        if self.connect_errors:
            raise self.connect_errors.pop(0)

    def wait_for_history(self) -> None:
        self.waited += 1

    def account_info(self) -> FakeAccountInfo:
        if self.info_errors:
            raise self.info_errors.pop(0)
        self.info_calls += 1
        if self.info_after is not None and self._already_switched():
            return self.info_after
        return self.info

    def _already_switched(self) -> bool:
        if self.switch_during_history:
            return self.switched_in_history
        return self.info_calls > self.switch_after

    def history_deals(self, start: datetime, end: datetime) -> Sequence[FakeDeal]:
        if self.history_errors:
            raise self.history_errors.pop(0)
        self.history_calls.append((start, end))
        # Щелчок по другому счёту приходится ровно на чтение истории: до этой строки
        # `account_info()` отвечает прежним счётом, после — новым.
        self.switched_in_history = self.switched_in_history or self.switch_during_history
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

    items: list[Assignment] = field(default_factory=list)
    batches: list[dict[str, Any]] = field(default_factory=list)
    heartbeats: list[HeartbeatAccount] = field(default_factory=list)
    beats: list[list[HeartbeatAccount]] = field(default_factory=list)
    refuse: Exception | None = None
    assignments_error: Exception | None = None
    heartbeat_error: Exception | None = None

    def assignments(self, collector_id: str) -> list[Assignment]:
        if self.assignments_error is not None:
            raise self.assignments_error
        return list(self.items)

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
        batch = list(accounts)
        self.beats.append(batch)
        if self.heartbeat_error is not None:
            raise self.heartbeat_error
        self.heartbeats.extend(batch)

    def said(self, account_id: str) -> HeartbeatAccount | None:
        """Последнее, что коллектор сказал про этот счёт."""
        for beat in reversed(self.heartbeats):
            if beat.account_id == account_id:
                return beat
        return None


@pytest.fixture(autouse=True)
def _no_secrets_between_tests() -> Iterator[None]:
    """Реестр секретов скраба — состояние процесса, а тесты его наполняют."""
    logging_setup.forget_secrets()
    yield
    logging_setup.forget_secrets()


@pytest.fixture
def settings(tmp_path: Any) -> CollectorSettings:
    return CollectorSettings(
        api_url="http://localhost:8000",
        collector_token=TOKEN,  # type: ignore[arg-type]
        collector_id=COLLECTOR_ID,
        sync_interval_seconds=60,
        heartbeat_interval_seconds=60,
        first_sync_days=3650,
        log_level="INFO",
        log_dir=tmp_path / "logs",
        state_dir=tmp_path / "state",
    )


def assignment_for(
    account_id: str = ACCOUNT_ID,
    *,
    login: int = LOGIN,
    server: str = SERVER,
    sync_requested_at: datetime | None = None,
    last_sync_at: datetime | None = None,
    status: str = "pending",
) -> Assignment:
    return Assignment(
        account_id=account_id,
        server=server,
        login=login,
        sync_requested_at=sync_requested_at,
        last_sync_at=last_sync_at,
        status=status,
    )


@pytest.fixture
def assignment() -> Assignment:
    return assignment_for()


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
