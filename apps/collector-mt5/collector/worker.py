"""Один счёт: цикл синхронизации через уже открытый терминал — `SPEC.md` §8.2, пункт 2.

Терминалом и подключением к нему владеет `main.py`: экземпляр `MetaTrader5` на машине
один, и открывает его человек (`X-66`, `T-07`). Здесь — только то, что коллектор делает
со счётом, который в этом терминале открыт: окно выборки, смещение часов брокера, сборка
и отправка батча, строка для карточки счёта.

Устройство модуля подчинено тому, что терминала на машине разработки нет. Цикл ходит в
терминал **только** через протокол `Terminal` и в API — только через `Api`, поэтому все
его решения проверяются на подделках. Непроверяемым остаётся `mt5_client.Mt5Terminal`, и
в нём нет ни одного решения.

⚠️ **Главный сторож этого модуля — вторая сверка счёта** (`_switched_away`). Первая
живёт в `main.py` и отвечает на вопрос «чей счёт мы собираемся спросить»; вторая стоит
после чтения истории и отвечает на другой — «чей счёт нам ответил». Между ними человек
вправе переключить счёт в терминале одним щелчком, и без второй сверки сделки чужого счёта
уехали бы в чужой журнал молча, а `deals` — append-only факты (`CLAUDE.md` §2).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Protocol

from collector import identity, messages, state, sync
from collector.api_client import ApiError, Assignment, IngestResult
from collector.config import CollectorSettings
from collector.logging_setup import get_logger
from collector.mt5_client import Terminal, TerminalError
from collector.payload import (
    RawAccountInfo,
    RawDeal,
    RawPosition,
    Rejected,
    build_batch,
    split_sendable,
    split_sendable_positions,
)

log = get_logger(__name__)


class Api(Protocol):
    """То, что цикл счёта берёт у API. `ApiClient` подходит под него структурно.

    Только отправка батча: assignments спрашивает и heartbeat собирает `main.py` — за все
    счета сразу, одним запросом (`SPEC.md` §8.2, пункт 1).
    """

    def send_deals(self, batch: dict[str, Any]) -> IngestResult: ...


STATE_RUNNING: Final = "running"
STATE_ERROR: Final = "error"
STATE_STOPPED: Final = "stopped"

# Что человек прочтёт на карточке счёта, когда смещения нет и батч уехать не может.
# Сверка часов при первом запуске — не поломка, а нормальный шаг, и `error` в этом месте
# каждый раз красил бы новый счёт в «требует внимания» на первую минуту жизни.
OFFSET_REPORTS: Final[dict[str, tuple[str, str]]] = {
    "waiting": (STATE_RUNNING, messages.OFFSET_PENDING),
    "disagreed": (STATE_RUNNING, messages.OFFSET_PENDING),
    "stale_quote": (STATE_ERROR, messages.OFFSET_UNKNOWN),
    "no_quote": (STATE_ERROR, messages.OFFSET_UNKNOWN),
    "out_of_range": (STATE_ERROR, messages.OFFSET_CLOCK_SKEW),
}

USD: Final = "USD"

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Report:
    """Что сказать про этот счёт в общем heartbeat'е (`SPEC.md` §5.3).

    `state=running` без сообщения означает «коллектор ведёт этот счёт»: `apply_heartbeat`
    двигает при нём только `last_heartbeat_at` и не трогает ни статус, ни текст на
    карточке. Текст ставит только `state=error` — другого канала до экрана нет.
    """

    state: str
    message: str | None = None
    terminal_login: int | None = None


@dataclass
class SyncState:
    """Что процесс помнит между тиками. Всё восстановимо: перезапуск ничего не теряет."""

    last_sync_at: datetime | None = None
    last_sent_at: datetime | None = None
    last_sent_ticket: int | None = None
    last_open_position_ids: frozenset[int] | None = None
    server_utc_offset_minutes: int | None = None
    # Кандидат в смещение, ждущий подтверждения второй котировкой (`sync.resolve_offset`).
    pending_offset: sync.OffsetProbe | None = None
    catch_up_done_at: datetime | None = None


@dataclass(frozen=True)
class OffsetOutcome:
    """Смещение брокера на этом тике либо причина, по которой батча не будет."""

    minutes: int | None
    report: Report | None


@dataclass
class AccountWorker:
    """Синхронизация одного счёта. Терминал и API приходят снаружи — иначе это не проверить."""

    account_id: str
    settings: CollectorSettings
    api: Api
    clock: Clock = utc_now
    state_file: Path | None = None
    _sync: SyncState = field(default_factory=SyncState, init=False)
    _offset_loaded: bool = field(default=False, init=False)

    def tick(self, terminal: Terminal, *, assignment: Assignment, info: RawAccountInfo) -> Report:
        """Один проход синхронизации счёта, который открыт в терминале прямо сейчас.

        `info` — тот самый снимок `account_info()`, по которому `main.py` уже опознал счёт.
        Он передаётся сюда, а не запрашивается заново, чтобы проверенный снимок и снимок,
        уехавший в батч, были одним и тем же объектом: два вызова дали бы два состояния,
        и проверить можно было бы одно, а отправить другое.

        `TerminalError` наружу не ловится: терминалом владеет `main.py`, он и решает, что
        делать с оборвавшейся связью.
        """
        currency = str(info.currency).strip().upper()
        if currency != USD:
            # SPEC.md 8.2: синк не выполняется вовсе. Чинится это не перезапуском, а
            # сменой счёта, и делает это человек.
            return Report(STATE_ERROR, messages.not_usd(currency))

        expected = identity.read_open_account(info)
        if expected is None:  # pragma: no cover — `main` опознал этот же снимок до нас
            return Report(STATE_ERROR, messages.ACCOUNT_UNREADABLE)
        self._remember_assignment(assignment)
        outcome = self._offset(terminal)
        if outcome.minutes is None:
            return outcome.report or Report(STATE_ERROR, messages.OFFSET_UNKNOWN)
        offset = outcome.minutes

        now = self.clock()
        window = sync.plan_window(
            now,
            last_sync_at=self._sync.last_sync_at,
            sync_requested_at=assignment.sync_requested_at,
            last_finished_at=self._sync.catch_up_done_at,
            first_sync_days=self.settings.first_sync_days,
        )
        if window.clock_skew:
            # Часы этой машины отстают от часов сервера. Окно уже починено (`plan_window`
            # берёт `min(last_sync_at, now)`), но без этой строки причина не видна нигде:
            # синк идёт, батчи уходят, а окно каждый раз считалось бы наизнанку.
            log.warning(
                "collector.clock_behind_server",
                account_id=self.account_id,
                last_sync_at=str(self._sync.last_sync_at),
                now=str(now),
            )
        start, end = sync.terminal_bounds(window, offset)
        raw_deals = terminal.history_deals(start, end)
        raw_positions = terminal.open_positions()

        switched = self._switched_away(terminal, expected)
        if switched is not None:
            return switched

        sendable, rejected = split_sendable(raw_deals)
        if rejected:
            log.error(
                "collector.deals_rejected_locally",
                account_id=self.account_id,
                count=len(rejected),
                tickets=[item.ticket for item in rejected[:20]],
                reasons=sorted({item.reason for item in rejected}),
            )
        open_positions, rejected_positions = split_sendable_positions(raw_positions)
        if rejected_positions:
            # Отдельной строкой, а не вместе со сделками: открытая позиция едет в каждом
            # чанке окна, поэтому негодная останавливала бы не один батч, а все подряд.
            log.error(
                "collector.positions_rejected_locally",
                account_id=self.account_id,
                count=len(rejected_positions),
                position_ids=[item.ticket for item in rejected_positions[:20]],
                reasons=sorted({item.reason for item in rejected_positions}),
            )

        deals = sync.sort_deals(sendable)
        open_ids = frozenset(position.identifier for position in open_positions)
        # Максимум по тикетам, а не последний в хронологии: порядок сортировки — по
        # времени, и совпадение «последний по времени = наибольший тикет» держится на
        # монотонности тикетов MT5, которую нам никто не обещал.
        newest = max((item.ticket for item in deals), default=None)
        decision = sync.decide_send(
            max_ticket=newest,
            last_sent_ticket=self._sync.last_sent_ticket,
            open_position_ids=open_ids,
            last_open_position_ids=self._sync.last_open_position_ids,
            last_sent_at=self._sync.last_sent_at,
            now=now,
        )
        if not decision.send:
            log.debug("collector.nothing_to_send", account_id=self.account_id)
            return Report(STATE_RUNNING, terminal_login=expected.login)

        refused = self._send(
            info=info,
            deals=deals,
            open_positions=open_positions,
            offset=offset,
            window_reason=window.reason,
            reason=str(decision.reason),
            now=now,
        )
        if refused is not None:
            return refused

        self._sync.last_sent_at = now
        self._sync.last_sync_at = now
        self._sync.last_open_position_ids = open_ids
        if newest is not None:
            self._sync.last_sent_ticket = newest
        if window.reason == "catch_up":
            self._sync.catch_up_done_at = now
        return Report(
            STATE_RUNNING,
            _running_message(rejected, rejected_positions),
            terminal_login=expected.login,
        )

    # -- сторож счёта ------------------------------------------------------------------

    def _switched_away(self, terminal: Terminal, expected: identity.OpenAccount) -> Report | None:
        """Тот же счёт в терминале, что и до чтения истории? `None` — да, можно отправлять.

        Второй запрос `account_info()` — это сторож, а не источник данных: в батч уезжает
        первый снимок, тот же самый, по которому счёт опознали. Здесь спрашивается ровно
        одно — не переключил ли человек счёт, пока терминал отдавал историю.
        """
        after = terminal.account_info()
        now_open = identity.read_open_account(after)
        if now_open is not None and identity.stayed_the_same(expected, now_open):
            return None
        # Нечитаемый ответ — тоже отказ: доказать, что счёт тот же, не удалось, а батч
        # уезжает только на доказанном.
        log.error(
            "collector.account_switched_mid_read",
            account_id=self.account_id,
            expected_login=expected.login,
            open_login=now_open.login if now_open is not None else None,
        )
        return Report(STATE_ERROR, messages.ACCOUNT_SWITCHED)

    # -- отправка ----------------------------------------------------------------------

    def _send(
        self,
        *,
        info: RawAccountInfo,
        deals: Sequence[RawDeal],
        open_positions: Sequence[RawPosition],
        offset: int,
        window_reason: str,
        reason: str,
        now: datetime,
    ) -> Report | None:
        """Отправить окно батчами по 5000. `None` — доехало; отчёт — нет, повторим тиком позже.

        Открытые позиции едут в **каждом** батче, а не только в последнем: пустой список
        по контракту означает «открытых нет», и промежуточный батч с пустым списком
        показал бы счёт без открытых позиций до прихода следующего.
        """
        chunks = sync.chunk(deals)
        for number, part in enumerate(chunks, start=1):
            try:
                batch = build_batch(
                    account_id=self.account_id,
                    server_utc_offset_minutes=offset,
                    account_info=info,
                    deals=part,
                    open_positions=open_positions,
                )
            except ValueError as error:
                # Сборка внутри `try` не из осторожности. Снаружи её исключение убивало бы
                # процесс молча: трейсбек уходит в `sys.excepthook`, то есть в консоль,
                # которой под Task Scheduler (`S1-10`) нет, — в файл лога не попадало бы
                # ничего.
                log.error(
                    "collector.batch_unbuildable",
                    account_id=self.account_id,
                    chunk=number,
                    of=len(chunks),
                    reason=str(error),
                )
                return Report(STATE_ERROR, messages.BATCH_UNBUILDABLE.format(reason=error))
            try:
                result = self.api.send_deals(batch)
            except ApiError as error:
                log.error(
                    "collector.batch_refused",
                    account_id=self.account_id,
                    chunk=number,
                    of=len(chunks),
                    code=error.code,
                    status=error.status,
                )
                return Report(STATE_ERROR, messages.API_REFUSED.format(message=error.message))
            _log_result(self.account_id, result, reason=reason, window=window_reason, at=now)
        return None

    # -- смещение часов брокера ------------------------------------------------------

    def _offset(self, terminal: Terminal) -> OffsetOutcome:
        """Смещение сервера брокера, с памятью между запусками (`SPEC.md` §6.3).

        Смещение обязательно в каждом батче, поэтому его отсутствие заканчивает тик — и
        тогда вместе с ним возвращается то, что человек прочтёт на карточке счёта.
        """
        try:
            tick_time = terminal.server_time()
        except TerminalError as error:
            log.warning(
                "collector.server_time_failed",
                account_id=self.account_id,
                reason=error.message,
                mt5_code=error.code,
                mt5_description=error.description,
            )
            tick_time = None
        known = self._remembered_offset()
        decision = sync.resolve_offset(
            tick_time, self.clock(), known=known, pending=self._sync.pending_offset
        )
        self._sync.pending_offset = decision.pending
        self._log_offset(decision, tick_time=tick_time, known=known)
        if decision.confirmed and decision.offset is not None:
            self._sync.server_utc_offset_minutes = decision.offset
            self._remember_offset(decision.offset)
        if decision.offset is not None:
            return OffsetOutcome(minutes=decision.offset, report=None)
        account_state, message = OFFSET_REPORTS.get(
            decision.status, (STATE_ERROR, messages.OFFSET_UNKNOWN)
        )
        return OffsetOutcome(
            minutes=None,
            report=Report(account_state, message.format(hours=_hours(tick_time, self.clock()))),
        )

    def _log_offset(
        self, decision: sync.OffsetDecision, *, tick_time: int | None, known: int | None
    ) -> None:
        """Отвергнутый кандидат обязан быть виден.

        Иначе отравленное состояние выглядит как тишина: коллектор каждую минуту получает
        правильное смещение, каждую минуту молча его выбрасывает, и в логе нет ни строки —
        ровно тот случай, когда «у друга не заработало», а понять причину нечем.
        """
        if decision.status == "confirmed":
            log.info(
                "collector.offset_confirmed",
                account_id=self.account_id,
                offset=decision.offset,
                previous=known,
            )
            return
        if decision.status in ("jump_refused", "disagreed", "out_of_range"):
            log.warning(
                "collector.offset_rejected",
                account_id=self.account_id,
                status=decision.status,
                candidate=(
                    sync.rounded_offset_minutes(tick_time, self.clock())
                    if tick_time is not None
                    else None
                ),
                known=known,
            )
            return
        if decision.status in ("waiting", "stale_quote", "no_quote"):
            log.debug(
                "collector.offset_unsettled",
                account_id=self.account_id,
                status=decision.status,
                known=known,
            )

    def _remembered_offset(self) -> int | None:
        """Смещение с прошлого запуска читается один раз, дальше живёт в памяти."""
        if self._sync.server_utc_offset_minutes is not None or self._offset_loaded:
            return self._sync.server_utc_offset_minutes
        self._offset_loaded = True
        if self.state_file is not None:
            self._sync.server_utc_offset_minutes = state.read_state(
                self.state_file
            ).server_utc_offset_minutes
        return self._sync.server_utc_offset_minutes

    def _remember_offset(self, offset: int) -> None:
        if self.state_file is None:
            return
        try:
            state.write_state(self.state_file, state.WorkerState(server_utc_offset_minutes=offset))
        except OSError as error:
            # Не повод останавливать синк: файл — кэш на случай закрытого рынка, и его
            # потеря стоит одного пропущенного окна, а не сделок.
            log.warning("collector.state_not_written", reason=type(error).__name__)

    def _remember_assignment(self, assignment: Assignment) -> None:
        """`last_sync_at` двигает сервер, и он же чинит окно после перезапуска коллектора."""
        if assignment.last_sync_at is not None:
            self._sync.last_sync_at = _later(self._sync.last_sync_at, assignment.last_sync_at)


def _running_message(
    rejected: Sequence[Rejected], rejected_positions: Sequence[Rejected] = ()
) -> str:
    """Состояние счёта одной строкой. Отбракованные названы тикетом, а не числом.

    Число сказало бы «что-то потерялось», и дальше человеку некуда идти. Тикет и причина
    дают точку входа: сделку видно в терминале, причину — в этом коде.
    """
    parts = [
        _dropped(template, items)
        for template, items in (
            (messages.DEALS_DROPPED, rejected),
            (messages.POSITIONS_DROPPED, rejected_positions),
        )
        if items
    ]
    if not parts:
        return messages.RUNNING
    return messages.fit(" ".join(parts))


def _dropped(template: str, items: Sequence[Rejected]) -> str:
    first = items[0]
    return template.format(count=len(items), ticket=first.ticket, reason=first.reason)


def _later(left: datetime | None, right: datetime) -> datetime:
    return right if left is None or right > left else left


def _hours(tick_time: int | None, now: datetime) -> str:
    """Расхождение часов сервера и машины в часах — единственная подстановка в отчёты."""
    if tick_time is None:
        return "?"
    return f"{round(sync.rounded_offset_minutes(tick_time, now) / 60):+d}"


def _log_result(
    account_id: str, result: IngestResult, *, reason: str, window: str, at: datetime
) -> None:
    log.info(
        "collector.batch_sent",
        account_id=account_id,
        reason=reason,
        window=window,
        received=result.received,
        inserted=result.inserted,
        duplicates=result.duplicates,
        positions_rebuilt=result.positions_rebuilt,
        sync_run_id=result.sync_run_id,
        at=at.isoformat(),
    )
