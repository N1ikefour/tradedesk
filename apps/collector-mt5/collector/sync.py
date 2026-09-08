"""Решения синхронизации: окно выборки, смещение часов брокера, отправлять ли батч.

Всё в этом модуле — чистые функции. Так сделано намеренно: проверить их на машине
разработки можно, а всё, что зовёт терминал, — нельзя. Чем больше решений живёт здесь,
тем меньше остаётся в непроверяемой части.

Опора на идемпотентность сервера — не оптимизация, а конструкция: окна намеренно
перекрываются (`SPEC.md` §8.2, `last_sync_at − 24h`), дубли снимает `POST /ingest/deals`
по естественному ключу. Поэтому состояние синхронизации не сохраняется на диск: после
перезапуска коллектор берёт `last_sync_at` из assignments, то есть с сервера, и снова
перезапрашивает сутки. Единственное, что переживает перезапуск, — смещение часов
брокера (`state.py`): его негде взять, пока рынок закрыт.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final, Literal, Protocol

# Перекрытие окна: следующий батч всегда захватывает сутки назад (SPEC.md 8.2).
OVERLAP: Final = timedelta(hours=24)
# Запас вперёд: часы сервера брокера идут не по UTC, и сделка «из будущего» относительно
# UTC — норма, а не аномалия.
LOOKAHEAD: Final = timedelta(days=1)
# Внеочередной синк по просьбе пользователя (кнопка «синхронизировать сейчас», SPEC.md 5.2).
CATCH_UP: Final = timedelta(days=30)
# Пустой батч раз в 10 минут, чтобы на экране счёта обновился `last_sync_at` (SPEC.md 8.2).
KEEPALIVE: Final = timedelta(minutes=10)

MAX_DEALS_PER_BATCH: Final = 5000

# Диапазон реальных зон IANA, он же граница контракта (`ingest-deals.schema.json`).
MIN_OFFSET_MINUTES: Final = -720
MAX_OFFSET_MINUTES: Final = 840
OFFSET_STEP_MINUTES: Final = 15
# На сколько смещение брокера вправе измениться разом. Переход на летнее время двигает
# часы на час; скачок больше означает, что котировка протухла и по ней считать нельзя.
MAX_OFFSET_JUMP_MINUTES: Final = 60

# Ретрай подключения к терминалу: удвоение до потолка в 15 минут (SPEC.md 8.2).
FIRST_RETRY_DELAY_SECONDS: Final = 5.0
MAX_RETRY_DELAY_SECONDS: Final = 900.0

WindowReason = Literal["first", "catch_up", "incremental"]
SendReason = Literal["first", "new_deals", "open_positions_changed", "keepalive"]


class Chronological(Protocol):
    """Минимум, по которому сортируются сделки: момент и тикет."""

    time_msc: int
    ticket: int


@dataclass(frozen=True)
class Window:
    """Отрезок в UTC, за который запрашивается история."""

    start: datetime
    end: datetime
    reason: WindowReason


@dataclass(frozen=True)
class SendDecision:
    """Отправлять ли батч и почему. Причина уезжает в лог — иначе тишину не объяснить."""

    send: bool
    reason: SendReason | None


def plan_window(
    now: datetime,
    *,
    last_sync_at: datetime | None,
    sync_requested_at: datetime | None,
    last_finished_at: datetime | None,
    first_sync_days: int,
) -> Window:
    """Какой отрезок истории тянуть на этом тике (SPEC.md 8.2, пункт 2).

    Порядок веток — по убыванию объёма: просьба пользователя перекрывает обычный шаг,
    а первый синк перекрывает всё. `last_sync_at` приходит из assignments, то есть с
    сервера: после перезапуска коллектора окно восстанавливается само.
    """
    end = now + LOOKAHEAD
    if last_sync_at is None:
        return Window(start=now - timedelta(days=first_sync_days), end=end, reason="first")
    if _catch_up_requested(sync_requested_at, last_sync_at=last_sync_at, done_at=last_finished_at):
        return Window(start=now - CATCH_UP, end=end, reason="catch_up")
    return Window(start=last_sync_at - OVERLAP, end=end, reason="incremental")


def _catch_up_requested(
    sync_requested_at: datetime | None,
    *,
    last_sync_at: datetime,
    done_at: datetime | None,
) -> bool:
    """Просьба свежее последнего синка и ещё не отработана этим процессом.

    Два условия, а не одно: `last_sync_at` обновляет сервер, `done_at` помнит процесс.
    Без второго коллектор гонял бы тридцатидневное окно каждую минуту, пока сервер не
    успел записать новый `last_sync_at`.
    """
    if sync_requested_at is None:
        return False
    if sync_requested_at <= last_sync_at:
        return False
    return done_at is None or sync_requested_at > done_at


def terminal_bounds(window: Window, offset_minutes: int | None) -> tuple[datetime, datetime]:
    """Границы окна в часах сервера брокера — в них `history_deals_get` считает время.

    Терминал сравнивает переданные границы с `deal.time`, а это часы брокера, не UTC.
    Смещение известно — сдвигаем ровно на него; неизвестно (самый первый синк) —
    расширяем на максимум из диапазона IANA. Лишние сутки в выборке ничего не стоят:
    вставка идемпотентна, а недобранная сделка потерялась бы молча.
    """
    if offset_minutes is None:
        pad = timedelta(minutes=MAX_OFFSET_MINUTES)
        return _naive(window.start - pad), _naive(window.end + pad)
    shift = timedelta(minutes=offset_minutes)
    return _naive(window.start + shift), _naive(window.end + shift)


def _naive(moment: datetime) -> datetime:
    """MetaTrader5 принимает `datetime` без зоны; зона в нём молча игнорируется."""
    return moment.astimezone(UTC).replace(tzinfo=None)


def offset_from_tick(tick_server_time: int, now_utc: datetime) -> int | None:
    """Смещение часов брокера по свежей котировке (SPEC.md 6.3). `None` — котировка стара.

    `offset = round((server_now − utc_now) / 15 мин) * 15 мин`. Округление до четверти
    часа заодно съедает возраст котировки в несколько минут — но только его. Котировка
    выходного дня отстаёт на десятки часов, и результат вылетает за диапазон реальных
    зон: такое значение отбрасывается, вместо того чтобы уехать в батч смещением.

    ⚠️ Дыра названа честно: тонкий рынок с котировкой пятичасовой давности даёт смещение,
    которое в диапазон укладывается и потому будет принято. От этого страхует
    `reconcile_offset`, а не эта функция.
    """
    server_now = datetime.fromtimestamp(tick_server_time, tz=UTC)
    minutes = (server_now - now_utc).total_seconds() / 60
    rounded = round(minutes / OFFSET_STEP_MINUTES) * OFFSET_STEP_MINUTES
    if not MIN_OFFSET_MINUTES <= rounded <= MAX_OFFSET_MINUTES:
        return None
    return int(rounded)


def reconcile_offset(candidate: int | None, last_known: int | None) -> int | None:
    """Свежее значение против запомненного: скачок больше часа — это не перевод часов.

    Брокер двигает часы на 60 минут при переходе на летнее время и никогда больше. Всё,
    что прыгнуло сильнее, — протухшая котировка, и лучше остаться на прежнем смещении,
    чем записать сделкам чужое время: `time_utc` уводит позицию в другой торговый день,
    а прошлые сделки не пересчитываются (`SPEC.md` §6.3).
    """
    if candidate is None:
        return last_known
    if last_known is None:
        return candidate
    if abs(candidate - last_known) > MAX_OFFSET_JUMP_MINUTES:
        return last_known
    return candidate


def sort_deals[C: Chronological](deals: Sequence[C]) -> list[C]:
    """Хронологический порядок: `(time_msc, ticket)` — тот же ключ, что у сборщика позиций."""
    return sorted(deals, key=lambda deal: (deal.time_msc, deal.ticket))


def chunk[T](deals: Sequence[T], size: int = MAX_DEALS_PER_BATCH) -> list[Sequence[T]]:
    """Разбить на батчи не длиннее лимита (`SPEC.md` §5.3): больше — `413`, а не отправка.

    Пустой список даёт один пустой батч: батч без сделок — законное сообщение «жив,
    открытые позиции такие», и на нём держится обновление `last_sync_at`.
    """
    if size < 1:
        raise ValueError("размер батча должен быть положительным")
    if not deals:
        empty: Sequence[T] = []
        return [empty]
    return [deals[start : start + size] for start in range(0, len(deals), size)]


def decide_send(
    *,
    max_ticket: int | None,
    last_sent_ticket: int | None,
    open_position_ids: frozenset[int],
    last_open_position_ids: frozenset[int] | None,
    last_sent_at: datetime | None,
    now: datetime,
    keepalive: timedelta = KEEPALIVE,
) -> SendDecision:
    """Есть ли что сказать серверу (SPEC.md 8.2, пункт 2).

    Три повода, ровно как в спеке: сделка новее отправленной, изменившийся набор открытых
    позиций, десять минут тишины. Без этого коллектор слал бы одно и то же каждую минуту,
    а `sync_runs` превратился бы в шум, в котором не видно настоящих синков.
    """
    if last_sent_at is None:
        return SendDecision(send=True, reason="first")
    if max_ticket is not None and (last_sent_ticket is None or max_ticket > last_sent_ticket):
        return SendDecision(send=True, reason="new_deals")
    if last_open_position_ids is None or open_position_ids != last_open_position_ids:
        return SendDecision(send=True, reason="open_positions_changed")
    if now - last_sent_at >= keepalive:
        return SendDecision(send=True, reason="keepalive")
    return SendDecision(send=False, reason=None)


def retry_delay_seconds(attempt: int) -> float:
    """Задержка перед попыткой №`attempt` подключиться к терминалу: удвоение до 15 минут."""
    if attempt < 1:
        raise ValueError("попытки нумеруются с единицы")
    return min(FIRST_RETRY_DELAY_SECONDS * 2 ** (attempt - 1), MAX_RETRY_DELAY_SECONDS)
