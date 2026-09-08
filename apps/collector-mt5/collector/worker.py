"""Один счёт: подключение к терминалу и цикл синхронизации — `SPEC.md` §8.2, пункт 2.

Ручной запуск:

    python -m collector.worker --account-id <uuid>

Менеджер процессов, который поднимает такой процесс на каждый счёт из assignments, —
`S1-09`; здесь один счёт и один процесс.

Устройство модуля подчинено тому, что терминала на машине разработки нет. Цикл ходит в
терминал **только** через протокол `Terminal` и в API — только через `ApiClient`, поэтому
все его решения проверяются на подделках: и «отправлять ли батч», и «что делать с
неверным паролем», и «сколько ждать перед повторной попыткой». Непроверяемым остаётся
`mt5_client.Mt5Terminal`, и в нём нет ни одного решения.

Heartbeat здесь — **по смене состояния**, а не по расписанию: периодический heartbeat и
опрос assignments живут в менеджере (`S1-09`). Без этих трёх строк неверный пароль не
доехал бы до экрана вовсе (`SPEC.md` §8.2, пункт 2).
"""

from __future__ import annotations

import argparse
import contextlib
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Protocol

from collector import messages, state, sync
from collector.api_client import (
    ApiClient,
    ApiError,
    Assignment,
    HeartbeatAccount,
    IngestResult,
)
from collector.config import (
    DEFAULT_ENV_FILENAME,
    CollectorSettings,
    ConfigError,
    load_settings,
    non_ascii_path_warning,
    platform_refusal,
)
from collector.logging_setup import account_log_name, get_logger, setup_logging
from collector.mt5_client import Credentials, Mt5Terminal, Terminal, TerminalError
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

    Протокол, а не сам клиент: подделка в тесте не обязана наследовать httpx-клиент, а
    цикл синхронизации проверяется только подделками — сети в тестах нет.
    """

    def assignments(self, collector_id: str) -> list[Assignment]: ...

    def send_deals(self, batch: dict[str, Any]) -> IngestResult: ...

    def heartbeat(self, collector_id: str, accounts: Iterable[HeartbeatAccount]) -> None: ...


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

EXIT_OK: Final = 0
EXIT_CONFIG: Final = 2
EXIT_PLATFORM: Final = 3
EXIT_ACCOUNT: Final = 4

Clock = Callable[[], datetime]
Sleep = Callable[[float], None]
TerminalFactory = Callable[[Assignment], Terminal]


def utc_now() -> datetime:
    return datetime.now(UTC)


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
    reported_state: str | None = None
    reported_message: str | None = None


@dataclass
class AccountWorker:
    """Цикл одного счёта. Терминал и API приходят снаружи — иначе это не проверить."""

    account_id: str
    settings: CollectorSettings
    api: Api
    terminal_factory: TerminalFactory
    clock: Clock = utc_now
    sleep: Sleep = time.sleep
    state_file: Path | None = None
    _terminal: Terminal | None = field(default=None, init=False)
    _sync: SyncState = field(default_factory=SyncState, init=False)
    _login: int | None = field(default=None, init=False)
    # Задание держится в памяти процесса ради переподключения: терминал вправе умереть
    # посреди суток работы, а пароль к тому моменту взять неоткуда. `repr=False` на
    # `Assignment.password` защищает его в кадрах стека; в файл и в лог он не попадает.
    _assignment_in_use: Assignment | None = field(default=None, init=False, repr=False)
    _max_connect_attempts: int = field(default=0, init=False)

    # -- запуск --------------------------------------------------------------------

    def run(self, *, max_ticks: int = 0, max_connect_attempts: int = 0) -> int:
        """Подключиться и крутить синхронизацию. Возврат — код выхода процесса.

        `max_ticks=0` — бесконечный цикл, как в бою. Число — столько итераций и выход;
        это и `--once`, и единственный способ проверить цикл тестом, не останавливая его
        исключением.
        """
        try:
            assignment = self._assignment()
        except ApiError as error:
            self._report(STATE_ERROR, error.message)
            log.error("collector.assignments_failed", reason=error.message)
            return EXIT_ACCOUNT
        if assignment is None:
            missing = messages.ASSIGNMENT_MISSING.format(account_id=self.account_id)
            self._report(STATE_ERROR, missing)
            return EXIT_ACCOUNT
        self._login = assignment.login
        self._assignment_in_use = assignment
        self._sync.last_sync_at = assignment.last_sync_at
        self._sync.server_utc_offset_minutes = self._remembered_offset()
        self._max_connect_attempts = max_connect_attempts

        if not self._connect(assignment, max_attempts=max_connect_attempts):
            return EXIT_ACCOUNT
        try:
            return self._loop(max_ticks=max_ticks)
        finally:
            self._disconnect()

    def _assignment(self) -> Assignment | None:
        """Задание на свой счёт. Пароль отсюда не уходит никуда, кроме `connect`."""
        for item in self.api.assignments(self.settings.collector_id):
            if item.account_id == self.account_id:
                return item
        return None

    def _connect(self, assignment: Assignment, *, max_attempts: int) -> bool:
        """Подключение с удвоением задержки до 15 минут (`SPEC.md` §8.2)."""
        attempt = 0
        while True:
            attempt += 1
            terminal = self.terminal_factory(assignment)
            try:
                terminal.connect()
                terminal.wait_for_history()
            except TerminalError as error:
                log.warning("collector.connect_failed", attempt=attempt, reason=error.message)
                self._report(STATE_ERROR, error.message)
                if max_attempts and attempt >= max_attempts:
                    return False
                self.sleep(sync.retry_delay_seconds(attempt))
                continue
            self._terminal = terminal
            log.info("collector.connected", account_id=self.account_id, attempt=attempt)
            return True

    def _terminal_lost(self, error: TerminalError) -> int | None:
        """Терминал отвалился посреди работы — переподключиться, а не жаловаться вечно.

        Терминал закрывают руками, он падает, машина уходит в сон. Без этой ветки процесс
        остался бы жив, каждую минуту слал бы одну и ту же ошибку и не синхронизировал
        ничего до тех пор, пока человек не заметит и не перезапустит его сам.
        """
        self._report(STATE_ERROR, error.message)
        log.warning("collector.terminal_lost", account_id=self.account_id, reason=error.message)
        if self._terminal is not None:
            # Закрытие мёртвого терминала само вправе отказать — это уже неважно.
            with contextlib.suppress(TerminalError):
                self._terminal.close()
            self._terminal = None
        assignment = self._assignment_in_use
        if assignment is None:  # pragma: no cover — `run` заполняет его до цикла
            return EXIT_ACCOUNT
        if not self._connect(assignment, max_attempts=self._max_connect_attempts):
            return EXIT_ACCOUNT
        return None

    def _disconnect(self) -> None:
        if self._terminal is not None:
            self._terminal.close()
            self._terminal = None
        self._report(STATE_STOPPED, messages.STOPPED)

    # -- цикл ----------------------------------------------------------------------

    def _loop(self, *, max_ticks: int) -> int:
        ticks = 0
        while True:
            code = self._tick()
            if code is not None:
                return code
            ticks += 1
            if max_ticks and ticks >= max_ticks:
                return EXIT_OK
            self.sleep(float(self.settings.sync_interval_seconds))

    def _tick(self) -> int | None:
        """Одна итерация. `None` — продолжаем, число — код выхода процесса."""
        terminal = self._require_terminal()
        try:
            info = terminal.account_info()
        except TerminalError as error:
            return self._terminal_lost(error)

        currency = str(info.currency).strip().upper()
        if currency != USD:
            # SPEC.md 8.2: синк не выполняется вовсе. Процесс остаётся жив и молчит —
            # починка тут не в перезапуске, а в смене счёта, и это делает человек.
            self._report(STATE_ERROR, messages.not_usd(currency))
            return EXIT_ACCOUNT

        offset = self._offset(terminal)
        if offset is None:
            return None

        now = self.clock()
        window = sync.plan_window(
            now,
            last_sync_at=self._sync.last_sync_at,
            sync_requested_at=self._requested_at(),
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
        try:
            raw_deals = terminal.history_deals(start, end)
            raw_positions = terminal.open_positions()
        except TerminalError as error:
            return self._terminal_lost(error)

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
            return None

        if not self._send(
            info=info,
            deals=deals,
            open_positions=open_positions,
            offset=offset,
            window_reason=window.reason,
            reason=str(decision.reason),
            now=now,
        ):
            return None

        self._sync.last_sent_at = now
        self._sync.last_sync_at = now
        self._sync.last_open_position_ids = open_ids
        if newest is not None:
            self._sync.last_sent_ticket = newest
        if window.reason == "catch_up":
            self._sync.catch_up_done_at = now
        self._report(STATE_RUNNING, _running_message(rejected, rejected_positions))
        return None

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
    ) -> bool:
        """Отправить окно батчами по 5000. `False` — не доехало, повторим на следующем тике.

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
                # ничего, а `S1-09` перезапускал бы процесс в краш-петлю без следа.
                log.error(
                    "collector.batch_unbuildable",
                    account_id=self.account_id,
                    chunk=number,
                    of=len(chunks),
                    reason=str(error),
                )
                self._report(STATE_ERROR, messages.BATCH_UNBUILDABLE.format(reason=error))
                return False
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
                self._report(STATE_ERROR, messages.API_REFUSED.format(message=error.message))
                return False
            _log_result(self.account_id, result, reason=reason, window=window_reason, at=now)
        return True

    # -- смещение часов брокера ------------------------------------------------------

    def _offset(self, terminal: Terminal) -> int | None:
        """Смещение сервера брокера, с памятью между запусками (`SPEC.md` §6.3).

        `None` — работать нечем; отчёт человеку уже отправлен. Смещение обязательно в
        каждом батче, поэтому тик на этом и заканчивается.
        """
        try:
            tick_time = terminal.server_time()
        except TerminalError as error:
            log.warning("collector.server_time_failed", reason=error.message)
            tick_time = None
        known = self._sync.server_utc_offset_minutes
        decision = sync.resolve_offset(
            tick_time, self.clock(), known=known, pending=self._sync.pending_offset
        )
        self._sync.pending_offset = decision.pending
        self._log_offset(decision, tick_time=tick_time, known=known)
        if decision.confirmed and decision.offset is not None:
            self._sync.server_utc_offset_minutes = decision.offset
            self._remember_offset(decision.offset)
        if decision.offset is None:
            account_state, message = OFFSET_REPORTS.get(
                decision.status, (STATE_ERROR, messages.OFFSET_UNKNOWN)
            )
            self._report(account_state, message.format(hours=_hours(tick_time, self.clock())))
        return decision.offset

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
        if self.state_file is None:
            return None
        return state.read_state(self.state_file).server_utc_offset_minutes

    def _remember_offset(self, offset: int) -> None:
        if self.state_file is None:
            return
        try:
            state.write_state(self.state_file, state.WorkerState(server_utc_offset_minutes=offset))
        except OSError as error:
            # Не повод останавливать синк: файл — кэш на случай закрытого рынка, и его
            # потеря стоит одного пропущенного окна, а не сделок.
            log.warning("collector.state_not_written", reason=type(error).__name__)

    def _requested_at(self) -> datetime | None:
        """Просьба о внеочередном синке приходит только из assignments (`SPEC.md` §5.2)."""
        try:
            assignment = self._assignment()
        except ApiError as error:
            log.warning("collector.assignments_unavailable", reason=error.message)
            return None
        if assignment is None:
            return None
        self._assignment_in_use = assignment
        if assignment.last_sync_at is not None:
            self._sync.last_sync_at = _later(self._sync.last_sync_at, assignment.last_sync_at)
        return assignment.sync_requested_at

    # -- служебное -------------------------------------------------------------------

    def _require_terminal(self) -> Terminal:
        if self._terminal is None:  # pragma: no cover — `run` подключается до цикла
            raise TerminalError(messages.TERMINAL_LOST)
        return self._terminal

    def _report(self, account_state: str, message: str | None) -> None:
        """Heartbeat по смене состояния. Повтор того же самого сервер не увидит.

        Молчание при неизменном состоянии — не экономия трафика: `status_message` на
        экране счёта переписывается каждым heartbeat, и поток одинаковых сообщений
        стирал бы историю ровно в тот момент, когда человек её читает.
        """
        if account_state == self._sync.reported_state and message == self._sync.reported_message:
            return
        self._sync.reported_state = account_state
        self._sync.reported_message = message
        try:
            self.api.heartbeat(
                self.settings.collector_id,
                [
                    HeartbeatAccount(
                        account_id=self.account_id,
                        state=account_state,
                        message=message,
                        terminal_login=self._login,
                    )
                ],
            )
        except ApiError as error:
            # Heartbeat, который не доехал, не имеет права уронить синк: сделки важнее
            # отметки о состоянии, и следующая попытка всё равно будет через минуту.
            log.warning("collector.heartbeat_failed", reason=error.message)
            self._sync.reported_state = None
            self._sync.reported_message = None


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


# --------------------------------------------------------------------------------------
# Точка входа
# --------------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="collector.worker",
        description="Синхронизация одного счёта MT5 с TradeDesk",
    )
    parser.add_argument("--account-id", required=True, help="UUID счёта в TradeDesk")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(DEFAULT_ENV_FILENAME),
        help=f"Путь к файлу настроек (по умолчанию {DEFAULT_ENV_FILENAME})",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Один проход синхронизации вместо бесконечного цикла",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    refusal = platform_refusal()
    if refusal is not None:
        print(refusal)
        return EXIT_PLATFORM

    try:
        settings = load_settings(args.env_file)
    except ConfigError as error:
        print(str(error))
        return EXIT_CONFIG

    setup_logging(
        log_file=settings.log_dir / account_log_name(args.account_id),
        level=settings.log_level,
        secrets=settings.secrets,
    )
    for path in (settings.mt5_terminal_exe, settings.mt5_portable_root):
        warning = non_ascii_path_warning(path)
        if warning is not None:
            log.warning("collector.non_ascii_path", message=warning)

    with ApiClient(settings) as api:
        worker = AccountWorker(
            account_id=args.account_id,
            settings=settings,
            api=api,
            terminal_factory=lambda assignment: Mt5Terminal(
                credentials=Credentials(
                    login=assignment.login,
                    server=assignment.server,
                    password=assignment.password,
                ),
                terminal_exe=settings.mt5_terminal_exe,
                portable_root=settings.mt5_portable_root,
                account_id=args.account_id,
            ),
            state_file=state.state_path(settings.mt5_portable_root / args.account_id),
        )
        try:
            return worker.run(max_ticks=1 if args.once else 0)
        except Exception as error:
            # Последний рубеж, и он про диагностику, а не про устойчивость: без него
            # неожиданное исключение уходит в `sys.excepthook`, то есть в консоль,
            # которой под Task Scheduler (`S1-10`) нет. В `account-<id>.log` не попадало
            # бы ничего, и краш-петля из-под `S1-09` не оставляла бы следа вовсе.
            log.exception("collector.crashed", account_id=args.account_id)
            print(messages.CRASHED.format(error=type(error).__name__))
            return EXIT_ACCOUNT


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
