"""Решения синхронизации: окно, смещение брокера, отправлять ли батч — SPEC.md 8.2, 6.3."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from collector import sync
from tests.conftest import FakeDeal, moment

NOW = moment()


# --------------------------------------------------------------------------------------
# Окно выборки
# --------------------------------------------------------------------------------------


def test_first_run_reaches_back_by_first_sync_days() -> None:
    window = sync.plan_window(
        NOW,
        last_sync_at=None,
        sync_requested_at=None,
        last_finished_at=None,
        first_sync_days=3650,
    )
    assert window.reason == "first"
    assert window.start == NOW - timedelta(days=3650)
    assert window.end == NOW + timedelta(days=1)


def test_regular_run_overlaps_the_previous_window_by_a_day() -> None:
    """Перекрытие намеренное: дубли снимает ингест по естественному ключу (skill ingest-mt5)."""
    last = NOW - timedelta(minutes=1)
    window = sync.plan_window(
        NOW,
        last_sync_at=last,
        sync_requested_at=None,
        last_finished_at=None,
        first_sync_days=3650,
    )
    assert window.reason == "incremental"
    assert window.start == last - timedelta(hours=24)


def test_restart_asks_for_the_same_window_again_instead_of_losing_it() -> None:
    """Перезапуск не создаёт дублей и не теряет сделок: `last_sync_at` берётся с сервера.

    Локального состояния синка нет намеренно — после перезапуска коллектор считает окно
    от того же `last_sync_at`, что и до него, и снова захватывает сутки назад.
    """
    last = NOW - timedelta(hours=3)
    before = sync.plan_window(
        NOW,
        last_sync_at=last,
        sync_requested_at=None,
        last_finished_at=None,
        first_sync_days=3650,
    )
    after_restart = sync.plan_window(
        NOW + timedelta(seconds=30),
        last_sync_at=last,
        sync_requested_at=None,
        last_finished_at=None,
        first_sync_days=3650,
    )
    assert before.start == after_restart.start


def test_user_request_widens_the_window_to_thirty_days() -> None:
    """Кнопка «синхронизировать сейчас» (SPEC.md 5.2) — внеочередной синк за 30 дней."""
    window = sync.plan_window(
        NOW,
        last_sync_at=NOW - timedelta(hours=1),
        sync_requested_at=NOW - timedelta(minutes=1),
        last_finished_at=None,
        first_sync_days=3650,
    )
    assert window.reason == "catch_up"
    assert window.start == NOW - timedelta(days=30)


def test_a_request_already_served_does_not_repeat_every_minute() -> None:
    """Иначе тридцатидневное окно гонялось бы каждую минуту, пока сервер не обновит счёт."""
    requested = NOW - timedelta(minutes=5)
    window = sync.plan_window(
        NOW,
        last_sync_at=NOW - timedelta(hours=1),
        sync_requested_at=requested,
        last_finished_at=NOW - timedelta(minutes=1),
        first_sync_days=3650,
    )
    assert window.reason == "incremental"


def test_a_stale_request_is_ignored() -> None:
    window = sync.plan_window(
        NOW,
        last_sync_at=NOW - timedelta(minutes=1),
        sync_requested_at=NOW - timedelta(days=2),
        last_finished_at=None,
        first_sync_days=3650,
    )
    assert window.reason == "incremental"


# --------------------------------------------------------------------------------------
# Границы в часах брокера
# --------------------------------------------------------------------------------------


def test_window_is_shifted_into_broker_hours() -> None:
    """`history_deals_get` сравнивает границы с `deal.time`, а это часы брокера, не UTC."""
    window = sync.Window(start=NOW, end=NOW + timedelta(days=1), reason="incremental")
    start, end = sync.terminal_bounds(window, 120)
    assert start == datetime(2026, 9, 2, 16, 3, 11)
    assert end == datetime(2026, 9, 3, 16, 3, 11)
    assert start.tzinfo is None


def test_unknown_offset_widens_the_window_instead_of_guessing() -> None:
    """Первый синк: смещения ещё нет. Лишние сутки бесплатны, недобранная сделка — нет."""
    window = sync.Window(start=NOW, end=NOW + timedelta(days=1), reason="first")
    start, end = sync.terminal_bounds(window, None)
    assert start < NOW.replace(tzinfo=None) - timedelta(hours=13)
    assert end > (NOW + timedelta(days=1)).replace(tzinfo=None) + timedelta(hours=13)


# --------------------------------------------------------------------------------------
# Смещение часов сервера брокера (SPEC.md 6.3)
# --------------------------------------------------------------------------------------


def test_offset_is_rounded_to_a_quarter_of_an_hour() -> None:
    """Выгрузка боевого счёта дала ровно +120 (docs/mt5-assumptions.md, допущение 6)."""
    tick = int((NOW + timedelta(minutes=120, seconds=17)).timestamp())
    assert sync.offset_from_tick(tick, NOW) == 120


def test_negative_offset_works_too() -> None:
    tick = int((NOW - timedelta(minutes=300)).timestamp())
    assert sync.offset_from_tick(tick, NOW) == -300


def test_a_weekend_quote_is_refused_instead_of_becoming_an_offset() -> None:
    """Котировка пятницы в воскресенье отстаёт на десятки часов — это не смещение зоны."""
    tick = int((NOW - timedelta(days=2)).timestamp())
    assert sync.offset_from_tick(tick, NOW) is None


def test_offset_beyond_the_real_zones_is_refused() -> None:
    """Диапазон IANA — он же граница контракта: значение вне его отвергла бы схема."""
    tick = int((NOW + timedelta(hours=20)).timestamp())
    assert sync.offset_from_tick(tick, NOW) is None


def test_daylight_saving_shift_is_accepted() -> None:
    assert sync.reconcile_offset(180, 120) == 180


def test_a_jump_bigger_than_daylight_saving_keeps_the_old_offset() -> None:
    """Прошлые сделки не пересчитываются (SPEC.md 6.3): чужое смещение испортит их навсегда."""
    assert sync.reconcile_offset(600, 120) == 120


def test_missing_candidate_falls_back_to_what_we_knew() -> None:
    """«Вне рабочего времени — последнее известное» — буква SPEC.md 6.3."""
    assert sync.reconcile_offset(None, 120) == 120


def test_nothing_known_at_all_stays_unknown() -> None:
    assert sync.reconcile_offset(None, None) is None


# --------------------------------------------------------------------------------------
# Отправлять или молчать
# --------------------------------------------------------------------------------------


def _decide(**overrides: object) -> sync.SendDecision:
    kwargs: dict[str, object] = {
        "max_ticket": 100,
        "last_sent_ticket": 100,
        "open_position_ids": frozenset({1}),
        "last_open_position_ids": frozenset({1}),
        "last_sent_at": NOW - timedelta(seconds=60),
        "now": NOW,
    }
    kwargs.update(overrides)
    return sync.decide_send(**kwargs)  # type: ignore[arg-type]


def test_first_pass_always_sends() -> None:
    assert _decide(last_sent_at=None).reason == "first"


def test_a_newer_ticket_sends() -> None:
    assert _decide(max_ticket=101).reason == "new_deals"


def test_a_changed_set_of_open_positions_sends() -> None:
    assert _decide(open_position_ids=frozenset({1, 2})).reason == "open_positions_changed"


def test_a_closed_position_sends_too() -> None:
    assert _decide(open_position_ids=frozenset()).reason == "open_positions_changed"


def test_ten_minutes_of_silence_send_an_empty_batch() -> None:
    """Иначе `last_sync_at` на экране счёта застывает и счёт выглядит отвалившимся."""
    assert _decide(last_sent_at=NOW - timedelta(minutes=10)).reason == "keepalive"


def test_nothing_new_stays_quiet() -> None:
    """Синк раз в минуту без повода превратил бы историю синков в шум."""
    decision = _decide()
    assert decision.send is False
    assert decision.reason is None


# --------------------------------------------------------------------------------------
# Порядок и размер батчей
# --------------------------------------------------------------------------------------


def test_deals_leave_in_chronological_order() -> None:
    """Ключ тот же, что у сборщика позиций: `(время, тикет)`."""
    deals = [
        FakeDeal(ticket=3, time_msc=2000),
        FakeDeal(ticket=1, time_msc=1000),
        FakeDeal(ticket=2, time_msc=1000),
    ]
    assert [deal.ticket for deal in sync.sort_deals(deals)] == [1, 2, 3]


def test_a_long_history_is_split_instead_of_getting_a_413() -> None:
    """SPEC.md 5.3: батч больше 5000 сделок сервер отвергает."""
    deals = [FakeDeal(ticket=n) for n in range(12_001)]
    parts = sync.chunk(deals)
    assert [len(part) for part in parts] == [5000, 5000, 2001]
    assert [deal.ticket for deal in parts[0]] == list(range(5000))


def test_an_empty_window_still_produces_one_batch() -> None:
    """Пустой батч — это «жив, открытых нет»; на нём обновляется `last_sync_at`."""
    assert sync.chunk([]) == [[]]


def test_chunk_size_must_be_positive() -> None:
    with pytest.raises(ValueError, match="положительным"):
        sync.chunk([FakeDeal()], size=0)


# --------------------------------------------------------------------------------------
# Ретрай подключения
# --------------------------------------------------------------------------------------


def test_retry_delay_doubles_up_to_fifteen_minutes() -> None:
    """SPEC.md 8.2: экспоненциальная задержка с потолком 15 минут."""
    delays = [sync.retry_delay_seconds(attempt) for attempt in range(1, 12)]
    assert delays[:4] == [5.0, 10.0, 20.0, 40.0]
    assert delays[-1] == sync.MAX_RETRY_DELAY_SECONDS
    assert max(delays) == 900.0


def test_attempts_are_numbered_from_one() -> None:
    with pytest.raises(ValueError, match="единицы"):
        sync.retry_delay_seconds(0)


def test_naive_bounds_carry_no_timezone() -> None:
    """MetaTrader5 принимает `datetime` без зоны и молча игнорирует её, если она есть."""
    window = sync.Window(
        start=datetime(2026, 9, 2, tzinfo=UTC),
        end=datetime(2026, 9, 3, tzinfo=UTC),
        reason="first",
    )
    for bound in sync.terminal_bounds(window, 0):
        assert bound.tzinfo is None
