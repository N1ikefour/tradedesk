"""Обёртка над библиотекой `MetaTrader5`. **Единственный непроверяемый модуль пакета.**

Здесь и только здесь коллектор разговаривает с терминалом. Всё, что можно было решить
без него, вынесено в `payload.py`, `sync.py` и `messages.py` — их проверяют тесты на
машине разработки. Этот файл на macOS не выполняется ни разу: `MetaTrader5` существует
только под Windows.

Отсюда два правила, которым модуль подчинён целиком.

1. **Никаких решений.** Функции забирают данные и переводят коды ошибок в человеческий
   текст через `messages`. Ни расчёта окон, ни отбора сделок, ни арифметики.
2. **Импорт библиотеки — внутри функции, а не наверху файла.** Иначе `worker.py` нельзя
   было бы даже импортировать на машине разработки, и вместе с ним стали бы
   непроверяемыми его собственные решения.

Права коллектора кончаются на чтении: ни одного вызова, отправляющего ордер, здесь нет и
быть не должно (`CLAUDE.md` §5, investor-пароль).
"""

from __future__ import annotations

import shutil
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Final, Protocol

from collector import messages
from collector.payload import RawAccountInfo, RawDeal, RawPosition

# Что не копируется в портабельный экземпляр. `config` — не оптимизация, а требование:
# там лежат сохранённые терминалом учётные данные исходной установки, и тащить их в
# папку каждого счёта незачем. Остальное терминал соберёт заново сам.
PORTABLE_SKIP: Final[frozenset[str]] = frozenset({"config", "bases", "logs", "tester"})

INITIALIZE_TIMEOUT_MS: Final = 60_000

# SPEC.md 8.3: после подключения ждать, пока история не перестанет расти между вызовами.
HISTORY_SETTLE_TIMEOUT_SECONDS: Final = 30.0
HISTORY_SETTLE_POLL_SECONDS: Final = 2.0

# Символы, по тику которых определяется время сервера (SPEC.md 6.3). Берётся самый свежий
# из доступных: чем ликвиднее инструмент, тем меньше возраст котировки, а возраст здесь —
# это ошибка в смещении.
TIME_PROBE_SYMBOLS: Final[tuple[str, ...]] = ("EURUSD", "XAUUSD", "GBPUSD", "USDJPY", "BTCUSD")


class TerminalError(Exception):
    """Отказ терминала, уже переведённый в человеческий текст."""

    def __init__(self, message: str, *, code: int = 0) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


@dataclass(frozen=True)
class Credentials:
    """Чем входить в терминал. Пароль — только в памяти процесса."""

    login: int
    server: str
    password: str


class Terminal(Protocol):
    """То, что нужно `worker.py` от терминала.

    Протокол объявлен затем, чтобы цикл синхронизации проверялся тестами на подделке:
    настоящую реализацию запустить негде.
    """

    def connect(self) -> None: ...

    def account_info(self) -> RawAccountInfo: ...

    def history_deals(self, start: datetime, end: datetime) -> Sequence[RawDeal]: ...

    def open_positions(self) -> Sequence[RawPosition]: ...

    def server_time(self) -> int | None: ...

    def wait_for_history(self) -> None: ...

    def close(self) -> None: ...


def import_mt5() -> ModuleType:
    """Библиотека терминала. Отсутствует — человекочитаемый отказ, а не `ImportError`."""
    try:
        import MetaTrader5
    except ImportError as error:
        raise TerminalError(messages.MT5_PACKAGE_MISSING) from error
    return MetaTrader5


def portable_dir(root: Path, account_id: str) -> Path:
    """Папка портабельного экземпляра счёта — `MT5_PORTABLE_ROOT\\<account_id>`."""
    return root / account_id


def skips_portable_entry(name: str) -> bool:
    """Не копировать ли эту папку в портабельный экземпляр."""
    return name.casefold() in PORTABLE_SKIP


def prepare_portable_dir(terminal_exe: Path, root: Path, account_id: str) -> Path:
    """Разложить копию терминала под счёт и вернуть путь к её `terminal64.exe`.

    Копия делается один раз: существующая папка означает, что счёт уже поднимался, и
    перезаписывать её нельзя — там настройки и кэш истории этого счёта.
    """
    if not terminal_exe.exists():
        raise TerminalError(messages.TERMINAL_EXE_MISSING.format(path=terminal_exe))
    destination = portable_dir(root, account_id)
    target_exe = destination / terminal_exe.name
    if target_exe.exists():
        return target_exe
    try:
        shutil.copytree(
            terminal_exe.parent,
            destination,
            ignore=lambda _directory, names: [name for name in names if skips_portable_entry(name)],
            dirs_exist_ok=True,
        )
    except OSError as error:
        raise TerminalError(
            messages.PORTABLE_COPY_FAILED.format(path=destination, reason=error.strerror or error)
        ) from error
    if not target_exe.exists():
        raise TerminalError(messages.TERMINAL_EXE_MISSING.format(path=target_exe))
    return target_exe


class Mt5Terminal:
    """Реальный терминал. Всё в этом классе выполняется только на Windows."""

    def __init__(
        self,
        *,
        credentials: Credentials,
        terminal_exe: Path,
        portable_root: Path,
        account_id: str,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._credentials = credentials
        self._terminal_exe = terminal_exe
        self._portable_root = portable_root
        self._account_id = account_id
        self._mt5: ModuleType | None = None
        self._exe_in_use: Path | None = None
        self._sleep = sleep

    # -- подключение ---------------------------------------------------------------

    def connect(self) -> None:
        mt5 = import_mt5()
        self._mt5 = mt5
        exe = prepare_portable_dir(self._terminal_exe, self._portable_root, self._account_id)
        self._exe_in_use = exe
        ok = mt5.initialize(
            path=str(exe),
            login=self._credentials.login,
            password=self._credentials.password,
            server=self._credentials.server,
            portable=True,
            timeout=INITIALIZE_TIMEOUT_MS,
        )
        if not ok:
            raise self._failure("connect")

    def close(self) -> None:
        if self._mt5 is not None:
            self._mt5.shutdown()
            self._mt5 = None

    # -- данные --------------------------------------------------------------------

    def account_info(self) -> RawAccountInfo:
        info = self._module().account_info()
        if info is None:
            raise self._failure("account_info")
        result: RawAccountInfo = info
        return result

    def history_deals(self, start: datetime, end: datetime) -> Sequence[RawDeal]:
        deals = self._module().history_deals_get(start, end)
        if deals is None:
            raise self._failure("history")
        return list(deals)

    def open_positions(self) -> Sequence[RawPosition]:
        positions = self._module().positions_get()
        if positions is None:
            # Пустой список открытых позиций MT5 отдаёт как `None` при коде 1 (успех) —
            # это норма, а не отказ, и путать её с обрывом связи нельзя.
            code, _ = self._module().last_error()
            if code == messages.RES_S_OK:
                return []
            raise self._failure("positions")
        return list(positions)

    def server_time(self) -> int | None:
        """Время сервера брокера секундами эпохи — по самой свежей котировке (SPEC.md 6.3).

        `None` — ни один пробный символ не дал тика. Гадать здесь нечем: смещение обязано
        приехать из данных, а не из настроек машины, на которой крутится терминал.
        """
        mt5 = self._module()
        freshest: int | None = None
        for symbol in TIME_PROBE_SYMBOLS:
            tick = mt5.symbol_info_tick(symbol)
            moment = getattr(tick, "time", None) if tick is not None else None
            if isinstance(moment, int) and moment > 0 and (freshest is None or moment > freshest):
                freshest = moment
        return freshest

    def wait_for_history(self) -> None:
        """Дать терминалу догрузить историю с сервера брокера (SPEC.md 8.3).

        Ждём, пока число сделок не перестанет расти между двумя вызовами, но не дольше
        30 секунд. Без этого первый батч уедет с половиной истории — вставка идемпотентна,
        так что данные не потеряются, но счёт покажет неполный журнал до следующего тика.
        """
        mt5 = self._module()
        start = datetime(1970, 1, 2, tzinfo=UTC).replace(tzinfo=None)
        end = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=365)
        previous = -1
        waited = 0.0
        while waited < HISTORY_SETTLE_TIMEOUT_SECONDS:
            total = mt5.history_deals_total(start, end)
            if not isinstance(total, int) or total < 0:
                return
            if total == previous:
                return
            previous = total
            self._sleep(HISTORY_SETTLE_POLL_SECONDS)
            waited += HISTORY_SETTLE_POLL_SECONDS

    # -- служебное -----------------------------------------------------------------

    def _module(self) -> ModuleType:
        if self._mt5 is None:
            raise TerminalError(messages.TERMINAL_LOST)
        return self._mt5

    def _failure(self, stage: messages.Stage) -> TerminalError:
        code, description = self._module().last_error()
        return TerminalError(
            messages.describe_mt5_failure(
                int(code),
                str(description),
                stage=stage,
                server=self._credentials.server,
                login=self._credentials.login,
                terminal_path=str(self._exe_in_use or self._terminal_exe),
            ),
            code=int(code),
        )
