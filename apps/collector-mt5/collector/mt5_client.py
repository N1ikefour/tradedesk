"""Обёртка над библиотекой `MetaTrader5`. **Единственный непроверяемый модуль пакета.**

Здесь и только здесь коллектор разговаривает с терминалом. Всё, что можно было решить
без него, вынесено в `payload.py`, `sync.py`, `identity.py` и `messages.py` — их проверяют
тесты на машине разработки. Этот файл на macOS не выполняется ни разу: `MetaTrader5`
существует только под Windows.

**Коллектор подключается к терминалу, который открыл человек** (`X-66`, `T-07`). Он не
запускает терминал, не делает его копий и не входит в счёт паролем: `mt5.initialize()`
зовётся без единого параметра, кроме таймаута, — ровно так, как это доказанно работает на
живой машине. Попытка передать `path=` и `portable=True` возвращала `(-10005, 'IPC
timeout')` всегда, в том числе к заведомо живому и доступному терминалу.

Отсюда два правила, которым модуль подчинён целиком.

1. **Никаких решений.** Функции забирают данные и переводят коды ошибок в человеческий
   текст через `messages`. Ни расчёта окон, ни отбора сделок, ни арифметики, ни ответа на
   вопрос «наш ли это счёт» — последний живёт в `identity.py`. Три решения, которые здесь
   всё-таки принимаются, вынесены в чистые функции модуля и проверены тестами: какой тик
   считать свежайшим (`freshest_tick_time`), означает ли `None` от `positions_get()`
   пустоту или отказ (`positions_mean_empty`), догрузилась ли история (`history_step`).
2. **Импорт библиотеки — внутри функции, а не наверху файла.** Иначе `worker.py` нельзя
   было бы даже импортировать на машине разработки, и вместе с ним стали бы
   непроверяемыми его собственные решения.

Права коллектора кончаются на чтении: ни одного вызова, отправляющего ордер, здесь нет и
быть не должно (`CLAUDE.md` §5).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime, timedelta
from types import ModuleType
from typing import Final, Literal, Protocol

from collector import messages
from collector.logging_setup import get_logger
from collector.payload import RawAccountInfo, RawDeal, RawPosition

log = get_logger(__name__)

INITIALIZE_TIMEOUT_MS: Final = 60_000

# SPEC.md 8.3: после подключения ждать, пока история не перестанет расти между вызовами.
HISTORY_SETTLE_TIMEOUT_SECONDS: Final = 30.0
HISTORY_SETTLE_POLL_SECONDS: Final = 2.0

# Символы, по тику которых определяется время сервера (SPEC.md 6.3). Берётся самый свежий
# из доступных: чем ликвиднее инструмент, тем меньше возраст котировки, а возраст здесь —
# это ошибка в смещении.
TIME_PROBE_SYMBOLS: Final[tuple[str, ...]] = ("EURUSD", "XAUUSD", "GBPUSD", "USDJPY", "BTCUSD")


class TerminalError(Exception):
    """Отказ терминала, уже переведённый в человеческий текст.

    `code` и `description` — то, что сказала библиотека. Человеку они не показываются
    (`X-67`: на карточке счёта нужен смысл, а не число), но в файл лога уходят отдельными
    полями: диагноз `X-66` занял час ровно потому, что кода в логе не было.
    """

    def __init__(self, message: str, *, code: int = 0, description: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.description = description


class Terminal(Protocol):
    """То, что нужно циклу синхронизации от терминала.

    Протокол объявлен затем, чтобы цикл проверялся тестами на подделке: настоящую
    реализацию запустить негде.
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


def freshest_tick_time(ticks: Iterable[object]) -> int | None:
    """Самое свежее время тика из пробных символов; `None` — ни одного годного.

    Решение, вынесенное из `Mt5Terminal.server_time`: чем ликвиднее инструмент, тем
    моложе его котировка, а возраст котировки — это прямая ошибка в смещении часов
    брокера. Отбраковка тика здесь же: `symbol_info_tick` по неизвестному брокеру символу
    вернёт `None`, а `time` у него бывает нулём — ноль означает «тика нет», а не «1970».
    """
    freshest: int | None = None
    for tick in ticks:
        moment = getattr(tick, "time", None) if tick is not None else None
        if not isinstance(moment, int) or isinstance(moment, bool) or moment <= 0:
            continue
        if freshest is None or moment > freshest:
            freshest = moment
    return freshest


def positions_mean_empty(last_error_code: int) -> bool:
    """`positions_get()` вернул `None` — это пустой список или отказ?

    Цена ошибки несимметрична и потому решение вынесено сюда, под тест: принять отказ за
    пустоту значит отправить батч без открытых позиций, то есть сказать серверу «открытых
    нет». Признак ровно один — код успеха в `last_error()`.
    """
    return last_error_code == messages.RES_S_OK


HistoryStep = Literal["settled", "growing", "unreadable"]


def history_step(total: object, previous: int) -> HistoryStep:
    """Догрузилась ли история между двумя опросами (`SPEC.md` §8.3).

    `unreadable` — библиотека вернула не число: ждать больше нечего, ждать нечем.
    """
    if not isinstance(total, int) or isinstance(total, bool) or total < 0:
        return "unreadable"
    return "settled" if total == previous else "growing"


class Mt5Terminal:
    """Открытый человеком терминал. Всё в этом классе выполняется только на Windows."""

    def __init__(self, *, sleep: Callable[[float], None] = time.sleep) -> None:
        self._mt5: ModuleType | None = None
        self._sleep = sleep

    # -- подключение ---------------------------------------------------------------

    def connect(self) -> None:
        """Подключиться к уже открытому терминалу — без пути, без входа в счёт.

        Ни `path=`, ни `portable=True`, ни `login`/`password`/`server`: измерено на живой
        машине (`X-66`), что с ними вызов возвращает `IPC timeout` всегда, а без них —
        `True` мгновенно. Чей счёт в этом терминале открыт, спрашивают отдельно
        (`account_info` плюс `identity.match_open_account`), и до ответа не отправляется
        ничего.
        """
        mt5 = import_mt5()
        self._mt5 = mt5
        if not mt5.initialize(timeout=INITIALIZE_TIMEOUT_MS):
            raise self._failure("connect")

    def close(self) -> None:
        """Отпустить канал до терминала.

        Окно терминала при этом не закрывается: терминал не наш, его открыл человек, и
        `shutdown()` рвёт только соединение библиотеки. До `X-66` здесь оставался жить
        портабельный экземпляр коллектора (допущение 36) — оставлять больше нечего.
        """
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
            if positions_mean_empty(int(code)):
                return []
            raise self._failure("positions")
        return list(positions)

    def server_time(self) -> int | None:
        """Время сервера брокера секундами эпохи — по самой свежей котировке (SPEC.md 6.3).

        `None` — ни один пробный символ не дал тика. Гадать здесь нечем: смещение обязано
        приехать из данных, а не из настроек машины, на которой крутится терминал.
        """
        mt5 = self._module()
        return freshest_tick_time(mt5.symbol_info_tick(symbol) for symbol in TIME_PROBE_SYMBOLS)

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
            step = history_step(total, previous)
            if step != "growing":
                return
            previous = int(total)
            self._sleep(HISTORY_SETTLE_POLL_SECONDS)
            waited += HISTORY_SETTLE_POLL_SECONDS
        # Выход по таймауту при всё ещё растущей истории. Молчать здесь нельзя: первый
        # батч уедет неполным, и единственный способ потом это понять — увидеть строку.
        log.warning(
            "collector.history_still_loading",
            deals_seen=previous,
            waited_seconds=waited,
        )

    # -- служебное -----------------------------------------------------------------

    def _module(self) -> ModuleType:
        if self._mt5 is None:
            raise TerminalError(messages.TERMINAL_LOST)
        return self._mt5

    def _failure(self, stage: messages.Stage) -> TerminalError:
        code, description = self._module().last_error()
        return TerminalError(
            messages.describe_mt5_failure(int(code), str(description), stage=stage),
            code=int(code),
            description=str(description),
        )
