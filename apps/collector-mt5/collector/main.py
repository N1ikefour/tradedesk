"""Коллектор целиком: один процесс, один терминал, один синхронизируемый счёт.

Запуск:

    python -m collector.main

Раз в `HEARTBEAT_INTERVAL_SECONDS` коллектор спрашивает `GET /internal/collector/assignments`,
подключается к **уже открытому** терминалу MetaTrader 5, узнаёт у него, какой счёт там
открыт, синхронизирует именно его и шлёт heartbeat за все свои счета сразу.

**Почему один процесс, а не пул.** До `X-66` здесь жил менеджер: процесс на счёт, копия
терминала на счёт, вход по паролю. Механизм не заработал ни разу — `initialize(path=…,
portable=True)` возвращал `IPC timeout` всегда, — а подключение к открытому терминалу
доказано работающим. Канал `MetaTrader5` при этом один на машину: `initialize()` без пути
цепляется к тому экземпляру, который найдёт, и второй процесс, зовущий `shutdown()`, рвёт
чужое соединение. Пул процессов над одним каналом означал бы N попыток отобрать его друг у
друга — и ни одного способа проверить это до Windows. Поэтому процесс один; заодно исчезли
`multiprocessing`, сироты `X-57` и пять сущностей, которым больше нечего разделять.

**Цена решения названа и принята** (`T-07`): синхронизируется тот счёт, который человек
открыл в терминале. Остальные ждут. Данные не теряются — окно выборки идёт от
`last_sync_at`, и счёт догоняет пропущенное целиком, когда в него войдут.

**Пока не доказано, что в терминале открыт наш счёт, не уезжает ничего** — `identity.py`.
Это не осторожность: библиотека не спрашивает, чей счёт нам нужен, и не сообщает, что
подключила не тот.
"""

from __future__ import annotations

import argparse
import contextlib
import signal
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import FrameType
from typing import Any, Final, Protocol

from collector import identity, messages, state
from collector.api_client import ApiClient, ApiError, Assignment, HeartbeatAccount, IngestResult
from collector.config import (
    DEFAULT_ENV_FILENAME,
    CollectorSettings,
    ConfigError,
    load_settings,
    non_ascii_path_warning,
    platform_refusal,
)
from collector.logging_setup import LOG_NAME, get_logger, setup_logging
from collector.mt5_client import Mt5Terminal, Terminal, TerminalError
from collector.payload import RawAccountInfo
from collector.worker import (
    STATE_ERROR,
    STATE_RUNNING,
    STATE_STOPPED,
    AccountWorker,
    Report,
)

log = get_logger(__name__)

EXIT_OK: Final = 0
# Коллектор упал сам. Отдельно от 2 и 3: те означают «эта машина никогда не заработает»,
# а этот — «поднимите коллектор заново».
EXIT_FAILURE: Final = 1
EXIT_CONFIG: Final = 2
EXIT_PLATFORM: Final = 3

# Ожидание между тиками режется на куски, чтобы Ctrl+C и SIGTERM не ждали целую минуту.
NAP_SLICE_SECONDS: Final = 1.0

# Просьба остановиться, положенная рядом с `collector.env` кем-то снаружи процесса.
#
# На Windows попросить чужой процесс выйти нечем: `SIGTERM` там не межпроцессный, а
# `CTRL_BREAK` доставляется только тому, кто присоединился к консоли жертвы, — то есть
# ценой собственной консоли. Всё остальное (`taskkill /F`, «Снять задачу») — это
# `TerminateProcess`: цикл до `_shutdown` не доходит и прощальный heartbeat не уходит.
# Файл — единственная просьба, которую коллектор может услышать сам.
STOP_FLAG_NAME: Final = "collector-stop.flag"

Sleep = Callable[[float], None]
Monotonic = Callable[[], float]
TerminalFactory = Callable[[], Terminal]


class Api(Protocol):
    """То, что коллектор берёт у API. `ApiClient` подходит под него структурно.

    Протокол, а не сам клиент: подделка в тесте не обязана наследовать httpx-клиент, а
    весь цикл проверяется только подделками — сети в тестах нет.
    """

    def assignments(self, collector_id: str) -> list[Assignment]: ...

    def send_deals(self, batch: dict[str, Any]) -> IngestResult: ...

    def heartbeat(self, collector_id: str, accounts: Iterable[HeartbeatAccount]) -> None: ...


@dataclass
class Collector:
    """Цикл коллектора. Терминал и сеть приходят снаружи — иначе это не проверить."""

    settings: CollectorSettings
    api: Api
    terminal_factory: TerminalFactory
    sleep: Sleep = time.sleep
    monotonic: Monotonic = time.monotonic
    # Куда смотреть в поисках просьбы остановиться. `None` — не смотреть вовсе.
    stop_flag: Path | None = None
    _terminal: Terminal | None = field(default=None, init=False)
    _workers: dict[str, AccountWorker] = field(default_factory=dict, init=False)
    # Счета последнего удавшегося опроса assignments. Молчание API их не отменяет.
    _watched: tuple[Assignment, ...] = field(default=(), init=False)
    _stopping: bool = field(default=False, init=False)
    # Чем закончился цикл, если исключением. Прощальный heartbeat зависит от этого.
    _crash: str | None = field(default=None, init=False)
    # Чей счёт был открыт в терминале на прошлом тике: строка в лог пишется на смену, а не
    # на каждый тик, иначе `collector.log` состоял бы из неё одной.
    _last_open: identity.OpenAccount | None = field(default=None, init=False)
    # Когда синхронизация в последний раз доходила до счёта, по монотонным часам.
    _synced_at: float | None = field(default=None, init=False)

    def run(self, *, max_ticks: int = 0) -> int:
        """Крутить цикл. `max_ticks=0` — бесконечно, как в бою; число — столько тиков."""
        log.info(
            "collector.started",
            collector_id=self.settings.collector_id,
            tick=self._tick_seconds(),
            sync_interval=self.settings.sync_interval_seconds,
            heartbeat_interval=self.settings.heartbeat_interval_seconds,
        )
        # Флаг от прошлой остановки убирается до первого тика: иначе коллектор прочёл бы
        # чужую просьбу и вышел через секунду после старта, не объяснив почему.
        self._forget_stop_flag()
        ticks = 0
        try:
            while not self._stopping:
                self._tick()
                ticks += 1
                if max_ticks and ticks >= max_ticks:
                    break
                self._nap()
        except Exception as error:
            # Единственный случай, когда о счёте некому рассказать буквально: коллектор
            # умирает, а `print` под Task Scheduler уходит в никуда. Прощальный heartbeat
            # отсюда — единственное, что доедет до карточки.
            self._crash = messages.CRASHED.format(error=type(error).__name__)
            raise
        finally:
            self._shutdown()
        return EXIT_OK

    def stop(self) -> None:
        """Попросить коллектор остановиться. Зовётся из обработчика сигнала."""
        self._stopping = True

    # -- один тик --------------------------------------------------------------------

    def _tick(self) -> None:
        assignments = self._assignments()
        if assignments is not None:
            self._watched = tuple(assignments)
            self._retire_gone(assignments)
        if not self._watched:
            # Счетов нет вовсе — heartbeat отправлять не за кого, и сказать об этом можно
            # только в файл лога. Самая частая причина — чужой COLLECTOR_ID.
            log.warning("collector.no_assignments", reason=messages.NO_ASSIGNMENTS)
            return
        self._send(self._reports())

    def _assignments(self) -> list[Assignment] | None:
        """Счета этого коллектора. `None` — API молчит, прежний список остаётся в силе.

        Молчание API не имеет права ничего отменять: одна неудачная минута иначе снимала бы
        все счета с наблюдения, а следующая возвращала бы их с полной перезагрузкой окна.
        Синхронизацию она при этом всё равно остановит — батч отправлять некуда.
        """
        try:
            return self.api.assignments(self.settings.collector_id)
        except ApiError as error:
            log.warning(
                "collector.assignments_unavailable",
                reason=error.message,
                code=error.code,
                status=error.status,
            )
            return None

    def _retire_gone(self, assignments: Sequence[Assignment]) -> None:
        """Счёт ушёл (пауза, архив, другой коллектор) — забыть, что мы о нём помнили.

        Помнить нечего, кроме состояния синка, и держать его дальше вредно: возвращённый
        из паузы счёт обязан взять `last_sync_at` с сервера, а не из головы коллектора.
        """
        live = {item.account_id for item in assignments}
        for account_id in [key for key in self._workers if key not in live]:
            del self._workers[account_id]
            log.info("collector.account_released", account_id=account_id)

    def _reports(self) -> list[HeartbeatAccount]:
        """Что сказать про каждый счёт на этом тике."""
        terminal, failure = self._ensure_terminal()
        if terminal is None:
            return self._all(failure or messages.TERMINAL_NOT_OPEN)
        try:
            info = terminal.account_info()
            open_account = self._open_account(info)
            self._note_open_account(open_account)
            match = identity.match_open_account(open_account, self._watch_list())
            if match.status == "ambiguous":
                log.error("collector.ambiguous_account", open_login=open_account.login)
                return self._all(messages.ambiguous_account(open_account.login))
            if match.account_id is None:
                return self._all(messages.unknown_account(open_account.login, open_account.server))
            if match.status == "server_mismatch":
                return self._server_mismatch(match.account_id, match, open_account)
            if not self._due_for_sync():
                # Тик пришёл за heartbeat'ом, а не за сделками: `HEARTBEAT_INTERVAL_SECONDS`
                # меньше `SYNC_INTERVAL_SECONDS`. Счёт опознан, состояние отправлено,
                # терминал не тревожим.
                return self._only_running(match.account_id, login=open_account.login)
            return self._sync(terminal, account_id=match.account_id, info=info)
        except TerminalError as error:
            return self._all(self._terminal_lost(error))

    def _sync(
        self, terminal: Terminal, *, account_id: str, info: RawAccountInfo
    ) -> list[HeartbeatAccount]:
        """Синхронизировать открытый счёт; остальным — `running` без сообщения.

        Молчание про ждущие счета — решение, а не забывчивость. `state=error` — единственный
        способ написать текст на карточку, и он же красит её в «требует внимания». Счёт,
        который просто ждёт своей очереди, — это **штатное** состояние новой схемы, и три
        карточки из четырёх, вечно требующие внимания, сделали бы этот статус нечитаемым.
        Чем счёт занят на самом деле, видно по `last_sync_at` на той же карточке.
        """
        assignment = self._assignment(account_id)
        if assignment is None:  # pragma: no cover — `match` берёт счёт из того же списка
            return self._all(messages.NO_ASSIGNMENTS)
        # Отметка ставится до попытки, а не после успеха: неудачная тоже была обращением к
        # терминалу, и считать её «не было» значило бы долбить сломанный терминал каждый
        # тик. Данные от этого не теряются — окно следующего синка начнётся там же.
        self._synced_at = self.monotonic()
        report = self._worker(account_id).tick(terminal, assignment=assignment, info=info)
        return [
            self._beat(item.account_id, report)
            if item.account_id == account_id
            else HeartbeatAccount(account_id=item.account_id, state=STATE_RUNNING)
            for item in self._watched
        ]

    def _server_mismatch(
        self, account_id: str, match: identity.Match, open_account: identity.OpenAccount
    ) -> list[HeartbeatAccount]:
        """Логин совпал, имя сервера — нет. Синхронизации нет, но причина видна на карточке.

        Сообщение адресное: чинится оно правкой одного поля в карточке этого счёта, и на
        остальных карточках было бы шумом.
        """
        text = messages.server_mismatch(
            open_account.login, actual=open_account.server, expected=match.expected_server
        )
        log.error(
            "collector.server_mismatch",
            account_id=account_id,
            open_login=open_account.login,
            open_server=open_account.server,
            expected_server=match.expected_server,
        )
        return [
            HeartbeatAccount(account_id=item.account_id, state=STATE_ERROR, message=text)
            if item.account_id == account_id
            else HeartbeatAccount(account_id=item.account_id, state=STATE_RUNNING)
            for item in self._watched
        ]

    def _all(self, message: str) -> list[HeartbeatAccount]:
        """Одна причина на все счета: синхронизировать нельзя ни один."""
        return [
            HeartbeatAccount(account_id=item.account_id, state=STATE_ERROR, message=message)
            for item in self._watched
        ]

    def _only_running(self, account_id: str, *, login: int) -> list[HeartbeatAccount]:
        """Все живы, синхронизации на этом тике не было. Сообщений ни у кого нет.

        `state=running` без текста не переписывает то, что стоит на карточке (`SPEC.md`
        §5.3): последняя причина, поставленная синком, остаётся, а `last_heartbeat_at`
        двигается — ровно то, зачем этот тик и пришёл.
        """
        return [
            HeartbeatAccount(
                account_id=item.account_id,
                state=STATE_RUNNING,
                terminal_login=login if item.account_id == account_id else None,
            )
            for item in self._watched
        ]

    @staticmethod
    def _beat(account_id: str, report: Report) -> HeartbeatAccount:
        return HeartbeatAccount(
            account_id=account_id,
            state=report.state,
            message=report.message,
            terminal_login=report.terminal_login,
        )

    # -- терминал ----------------------------------------------------------------------

    def _ensure_terminal(self) -> tuple[Terminal | None, str | None]:
        """Подключиться к открытому терминалу. Отказ — не исключение, а обычная ветка.

        Повторная попытка — это следующий тик, и другого ретрая здесь нет намеренно.
        Экспоненциальная задержка (до `X-66` — до 15 минут) имела смысл, пока коллектор
        **запускал** терминал: там повтор стоил дорого. Теперь отказ означает «человек ещё
        не открыл MetaTrader 5», и правильный ответ на это — попробовать через минуту, а не
        через четверть часа после того, как он его открыл.
        """
        if self._terminal is not None:
            return self._terminal, None
        terminal = self.terminal_factory()
        try:
            terminal.connect()
            terminal.wait_for_history()
        except TerminalError as error:
            log.warning(
                "collector.connect_failed",
                reason=error.message,
                mt5_code=error.code,
                mt5_description=error.description,
            )
            with contextlib.suppress(TerminalError):
                terminal.close()
            return None, error.message
        self._terminal = terminal
        self._last_open = None
        log.info("collector.connected")
        return terminal, None

    def _terminal_lost(self, error: TerminalError) -> str:
        """Терминал отвалился посреди работы: закрыли руками, упал, машина уснула."""
        log.warning(
            "collector.terminal_lost",
            reason=error.message,
            mt5_code=error.code,
            mt5_description=error.description,
        )
        self._release_terminal()
        return error.message

    def _release_terminal(self) -> None:
        if self._terminal is None:
            return
        # Закрытие мёртвого терминала само вправе отказать — это уже неважно.
        with contextlib.suppress(TerminalError):
            self._terminal.close()
        self._terminal = None
        self._last_open = None

    def _note_open_account(self, open_account: identity.OpenAccount) -> None:
        if self._last_open == open_account:
            return
        self._last_open = open_account
        log.info(
            "collector.terminal_account",
            login=open_account.login,
            server=open_account.server,
        )

    # -- служебное ---------------------------------------------------------------------

    @staticmethod
    def _open_account(info: RawAccountInfo) -> identity.OpenAccount:
        """Кто открыт в терминале. Нечисловой `login` — отказ словами, а не краш процесса.

        Соседние непереводимые поля `account_info` (`margin_mode`) уже превращаются в текст
        на карточке, и `login` не имеет права быть исключением: иначе один и тот же класс
        отказа выглядит то сообщением, то краш-петлёй под Планировщиком.
        """
        open_account = identity.read_open_account(info)
        if open_account is None:
            raise TerminalError(messages.ACCOUNT_UNREADABLE)
        return open_account

    def _watch_list(self) -> list[identity.Watched]:
        return [
            identity.Watched(account_id=item.account_id, login=item.login, server=item.server)
            for item in self._watched
        ]

    def _assignment(self, account_id: str) -> Assignment | None:
        for item in self._watched:
            if item.account_id == account_id:
                return item
        return None

    def _worker(self, account_id: str) -> AccountWorker:
        worker = self._workers.get(account_id)
        if worker is None:
            worker = AccountWorker(
                account_id=account_id,
                settings=self.settings,
                api=self.api,
                state_file=state.state_path(self.settings.state_dir, account_id),
            )
            self._workers[account_id] = worker
        return worker

    def _send(self, accounts: Sequence[HeartbeatAccount]) -> None:
        if not accounts:
            return
        try:
            self.api.heartbeat(self.settings.collector_id, accounts)
        except ApiError as error:
            # Heartbeat, который не доехал, не имеет права остановить синхронизацию:
            # сделки важнее отметки о состоянии, а она повторится через минуту.
            log.warning(
                "collector.heartbeat_failed",
                reason=error.message,
                code=error.code,
                status=error.status,
            )

    def _tick_seconds(self) -> int:
        """Период цикла: меньший из двух интервалов `collector.env`.

        Цикл один, а интервала в настройках два, и оба означают своё: `SYNC_INTERVAL_SECONDS` —
        как часто спрашивать терминал, `HEARTBEAT_INTERVAL_SECONDS` — как часто отмечаться
        у TradeDesk (молчание дольше пяти минут уводит счёт в «коллектор не на связи»,
        `SPEC.md` §10). Взять один и забыть второй значило бы оставить в `collector.env`
        поле, которое ни на что не влияет, — то есть соврать человеку в файле, который он
        правит руками.
        """
        return min(self.settings.sync_interval_seconds, self.settings.heartbeat_interval_seconds)

    def _due_for_sync(self) -> bool:
        """Пора ли снова спрашивать терминал."""
        if self._synced_at is None:
            return True
        return self.monotonic() - self._synced_at >= self.settings.sync_interval_seconds

    def _nap(self) -> None:
        """Пауза между тиками, порезанная на куски: сигнал не должен ждать целую минуту."""
        remaining = float(self._tick_seconds())
        while remaining > 0 and not self._stopping:
            nap = min(NAP_SLICE_SECONDS, remaining)
            self.sleep(nap)
            remaining -= nap
            if self._stop_requested():
                log.info("collector.stop_requested", flag=str(self.stop_flag))
                self.stop()

    def _stop_requested(self) -> bool:
        if self.stop_flag is None:
            return False
        try:
            return self.stop_flag.exists()
        except OSError:
            # Недоступный путь — это «просьбы нет», а не повод уронить коллектор: файл
            # кладёт кто-то другой, и его права нам не подчиняются.
            return False

    def _forget_stop_flag(self) -> None:
        if self.stop_flag is None:
            return
        with contextlib.suppress(OSError):
            self.stop_flag.unlink(missing_ok=True)

    def _shutdown(self) -> None:
        """Отпустить терминал и сказать о себе. Зовётся и при штатном выходе, и при краше.

        Штатная остановка — `state=stopped`: она статуса не меняет (`accounts.service`), и
        это верно, потому что коллектор остановил человек. Крах — `state=error` с текстом
        `CRASHED`: иначе о нём не узнал бы никто, кроме файла лога, а на карточке через пять
        минут появилось бы «коллектор не на связи» вместо причины.
        """
        self._release_terminal()
        account_state = STATE_ERROR if self._crash is not None else STATE_STOPPED
        message = self._crash if self._crash is not None else messages.STOPPED
        self._send(
            [
                HeartbeatAccount(account_id=item.account_id, state=account_state, message=message)
                for item in self._watched
            ]
        )
        # Просьба выполнена: файл убирается здесь, а не только на старте, — иначе он
        # остановил бы следующий запуск, сделанный человеком тут же, следом.
        self._forget_stop_flag()
        log.info("collector.stopped", accounts=len(self._watched), crashed=bool(self._crash))


# --------------------------------------------------------------------------------------
# Точка входа
# --------------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="collector.main",
        description="Синхронизация MT5 с TradeDesk: тот счёт, который открыт в терминале",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(DEFAULT_ENV_FILENAME),
        help=f"Путь к файлу настроек (по умолчанию {DEFAULT_ENV_FILENAME})",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help=(
            "Один тик и выход: спросить задания, подключиться к открытому терминалу и "
            "синхронизировать открытый счёт один раз"
        ),
    )
    return parser


def install_signal_handlers(collector: Collector) -> None:
    """Ctrl+C и `SIGTERM` гасят коллектор по-человечески: цикл доходит до `_shutdown`.

    ⚠️ На Windows настоящий сигнал доходит только от консоли (`SIGINT`, `SIGBREAK`).
    `taskkill /F` и «Снять задачу» — то есть обычный способ остановки под Task Scheduler —
    это `TerminateProcess`: ни обработчика, ни `atexit`, ни `finally`. Поэтому снаружи
    коллектор просят выйти файлом (`STOP_FLAG_NAME`), а не сигналом: это единственная
    дорога к `_shutdown` для того, кто не сидит в его консоли.
    """

    def handler(signal_number: int, _frame: FrameType | None) -> None:
        log.info("collector.signal", signal=signal_number)
        collector.stop()

    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        number = getattr(signal, name, None)
        if number is None:
            continue
        with contextlib.suppress(ValueError, OSError):
            signal.signal(number, handler)


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
        log_file=settings.log_dir / LOG_NAME,
        level=settings.log_level,
        secrets=settings.secrets,
    )
    for path in (settings.log_dir, settings.state_dir):
        warning = non_ascii_path_warning(path)
        if warning is not None:
            log.warning("collector.non_ascii_path", message=warning)

    env_file = args.env_file.resolve()
    with ApiClient(settings) as api:
        collector = Collector(
            settings=settings,
            api=api,
            terminal_factory=Mt5Terminal,
            stop_flag=env_file.parent / STOP_FLAG_NAME,
        )
        install_signal_handlers(collector)
        try:
            return collector.run(max_ticks=1 if args.once else 0)
        except KeyboardInterrupt:
            log.info("collector.interrupted")
            return EXIT_OK
        except Exception as error:
            # Последний рубеж, и он про диагностику, а не про устойчивость: под Task
            # Scheduler (`S1-10`) консоли нет, и трейсбек из `sys.excepthook` не попал бы
            # никуда — краш-петля не оставляла бы следа вовсе.
            log.exception("collector.crashed")
            print(messages.CRASHED.format(error=type(error).__name__))
            return EXIT_FAILURE


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
