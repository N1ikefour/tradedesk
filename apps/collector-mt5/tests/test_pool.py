"""Решения менеджера процессов — `SPEC.md` §8.2, пункт 1.

Здесь нет ни процессов, ни сети: проверяется то, что менеджер **решает**. На машине
разработки это единственная часть `S1-09`, которую можно проверить целиком, — и она же
единственная, в которой есть что ломать.
"""

from __future__ import annotations

import pytest

from collector import pool
from collector.worker import EXIT_ACCOUNT, EXIT_CONFIG, EXIT_OK, EXIT_PLATFORM

A, B, C, D = "acc-a", "acc-b", "acc-c", "acc-d"

# Смерть, о которой процесс счёта сказать не успел: убит системой. Именно она, а не код 4,
# доводит человека до сообщений менеджера — код 4 означает, что причина уже названа.
CRASH = -9


# --------------------------------------------------------------------------------------
# Раздача мест
# --------------------------------------------------------------------------------------


def test_empty_collector_takes_everything_that_fits() -> None:
    plan = pool.plan_slots(held=(), assigned=[A, B], limit=3)
    assert plan.take == (A, B)
    assert plan.keep == ()
    assert plan.release == ()
    assert plan.over_limit == ()


def test_two_accounts_at_once() -> None:
    """DoD `S1-09`: два счёта одновременно — два места, и оба заняты."""
    first = pool.plan_slots(held=(), assigned=[A, B], limit=3)
    second = pool.plan_slots(held=first.take, assigned=[A, B], limit=3)
    assert second.keep == (A, B)
    assert second.take == ()


def test_account_gone_from_assignments_is_released() -> None:
    """Пауза и архив выглядят одинаково: счёт просто исчез из assignments (`SPEC.md` §5.6)."""
    plan = pool.plan_slots(held=(A, B), assigned=[B], limit=3)
    assert plan.release == (A,)
    assert plan.keep == (B,)


def test_fourth_account_is_named_not_swallowed() -> None:
    """⚠️ `SPEC.md` §12: превышение лимита обязано быть видно человеку поимённо.

    Первому пользователю нужно четыре счёта, а значение по умолчанию — три.
    """
    plan = pool.plan_slots(held=(), assigned=[A, B, C, D], limit=3)
    assert plan.take == (A, B, C)
    assert plan.over_limit == (D,)


def test_over_limit_does_not_wander_between_accounts() -> None:
    """Кто именно сверх лимита — один и тот же ответ от тика к тику.

    Иначе человек каждую минуту читал бы новую причину на новом счёте, и ни одна из них
    не была бы правдой дольше минуты.
    """
    held = pool.plan_slots(held=(), assigned=[A, B, C, D], limit=3).take
    for _ in range(5):
        plan = pool.plan_slots(held=held, assigned=[A, B, C, D], limit=3)
        assert plan.over_limit == (D,)
        assert plan.take == ()
        held = plan.keep


def test_working_account_keeps_its_slot_when_the_server_reorders_the_list() -> None:
    """Порядок ответа сервера не отбирает место у того, кто уже работает."""
    plan = pool.plan_slots(held=(A, B, C), assigned=[D, C, B, A], limit=3)
    assert plan.keep == (A, B, C)
    assert plan.take == ()
    assert plan.over_limit == (D,)


def test_freed_slot_goes_to_the_account_that_waited() -> None:
    """Счёт ушёл на паузу — его место достаётся тому, кому не хватило."""
    plan = pool.plan_slots(held=(A, B, C), assigned=[A, B, D], limit=3)
    assert plan.release == (C,)
    assert plan.take == (D,)
    assert plan.over_limit == ()


def test_dead_process_keeps_the_slot_until_the_account_disappears() -> None:
    """Место держится за счётом, а не за живым процессом.

    Менеджер зовёт `plan_slots` со **всеми** своими счетами, включая тех, чей процесс
    сейчас мёртв и ждёт перезапуска: иначе четвёртый счёт занимал бы место на время
    перезапуска, а вернувшийся первый оказывался бы сверх лимита.
    """
    plan = pool.plan_slots(held=(A, B, C), assigned=[A, B, C, D], limit=3)
    assert plan.keep == (A, B, C)
    assert plan.over_limit == (D,)


def test_lower_limit_releases_the_youngest_slots_and_names_them() -> None:
    plan = pool.plan_slots(held=(A, B, C), assigned=[A, B, C], limit=2)
    assert plan.keep == (A, B)
    assert plan.release == (C,)
    assert plan.over_limit == (C,)


def test_duplicates_in_the_answer_do_not_eat_slots() -> None:
    plan = pool.plan_slots(held=(), assigned=[A, A, B], limit=2)
    assert plan.take == (A, B)
    assert plan.over_limit == ()


def test_sets_never_overlap() -> None:
    plan = pool.plan_slots(held=(A, B, C), assigned=[B, C, D], limit=2)
    groups = (plan.keep, plan.take, plan.over_limit)
    seen = [account_id for group in groups for account_id in group]
    assert len(seen) == len(set(seen))
    assert A in plan.release


def test_limit_below_one_is_a_programming_error() -> None:
    with pytest.raises(ValueError):
        pool.plan_slots(held=(), assigned=[A], limit=0)


# --------------------------------------------------------------------------------------
# Смерть процесса и перезапуски
# --------------------------------------------------------------------------------------


def test_first_crash_schedules_a_restart() -> None:
    health = pool.after_exit(pool.HEALTHY, exit_code=CRASH, lived_seconds=1.0, now=100.0)
    assert health.failures == 1
    assert not health.exhausted
    assert health.retry_after == 100.0 + pool.FIRST_RESTART_DELAY_SECONDS
    assert health.status == "restarting"


def test_restart_waits_out_its_delay() -> None:
    health = pool.after_exit(pool.HEALTHY, exit_code=CRASH, lived_seconds=1.0, now=100.0)
    assert not pool.may_start(health, now=100.0)
    assert pool.may_start(health, now=100.0 + pool.FIRST_RESTART_DELAY_SECONDS)


def test_the_delays_the_policy_actually_uses_are_five_to_eighty_seconds() -> None:
    """⚠️ Потолок в 15 минут при `MAX_RESTARTS=5` недостижим, и `SPEC.md` §8.2 говорит это.

    Тест фиксирует **исполняемый** ряд, а не форму функции: девятого падения политика не
    допускает, и обещать человеку паузу до четверти часа было бы неправдой.
    """
    used = [pool.restart_delay_seconds(number) for number in range(1, pool.MAX_RESTARTS + 1)]
    assert used == [5.0, 10.0, 20.0, 40.0, 80.0]
    assert max(used) < pool.MAX_RESTART_DELAY_SECONDS


def test_delay_doubles_and_stops_at_fifteen_minutes() -> None:
    """Ограничитель формулы: он сработает, только если вырастет `MAX_RESTARTS`."""
    delays = [pool.restart_delay_seconds(number) for number in range(1, 12)]
    assert delays[:4] == [5.0, 10.0, 20.0, 40.0]
    assert delays[-1] == pool.MAX_RESTART_DELAY_SECONDS
    assert delays == sorted(delays)


def test_restarts_are_counted_and_run_out() -> None:
    """Пять перезапусков подряд, шестое падение — сдаёмся и говорим об этом."""
    health = pool.HEALTHY
    for _ in range(pool.MAX_RESTARTS):
        health = pool.after_exit(health, exit_code=CRASH, lived_seconds=0.5, now=0.0)
        assert not health.exhausted
        assert pool.may_start(health, now=1_000_000.0)
    health = pool.after_exit(health, exit_code=CRASH, lived_seconds=0.5, now=0.0)
    assert health.exhausted
    assert health.status == "exhausted"
    assert not pool.may_start(health, now=1_000_000.0)


# --------------------------------------------------------------------------------------
# Кто рассказывает человеку причину
# --------------------------------------------------------------------------------------


def test_a_process_that_named_its_reason_leaves_the_manager_nothing_to_say() -> None:
    """Код 4 значит «я уже отправил heartbeat с точной причиной» (`worker.py`).

    Менеджеру после такого сказать нечего: его текст общий («пришлите файл лога»), а на
    карточке стоит конкретное — «счёт не в USD», «батч отвергнут». Перекрыть одно другим
    значит потерять диагноз.
    """
    health = pool.after_exit(pool.HEALTHY, exit_code=EXIT_ACCOUNT, lived_seconds=1.0, now=0.0)
    assert health.explained
    assert health.status == "explained"
    assert pool.may_start(health, now=1_000_000.0)


def test_the_reason_outlives_the_restart_budget() -> None:
    """Перезапуски кончились, а причина осталась верной: счёт как был в евро, так и остался."""
    health = pool.HEALTHY
    for _ in range(pool.MAX_RESTARTS + 1):
        health = pool.after_exit(health, exit_code=EXIT_ACCOUNT, lived_seconds=0.5, now=0.0)
    assert health.exhausted
    assert health.status == "explained"
    assert not pool.may_start(health, now=1_000_000.0)


def test_an_unknown_exit_code_is_not_taken_for_an_explanation() -> None:
    """Система не сообщила код — значит, никто ничего человеку не объяснял."""
    health = pool.after_exit(pool.HEALTHY, exit_code=None, lived_seconds=0.5, now=0.0)
    assert not health.explained
    assert health.status == "restarting"
    assert health.last_exit_code is None


def test_a_process_that_never_started_has_its_own_story() -> None:
    """`spawn` отказал: кода выхода нет, файла лога счёта нет — просить его бессмысленно."""
    health = pool.after_failed_start(pool.HEALTHY, now=100.0)
    assert health.status == "not_started"
    assert health.failures == 1
    assert not health.started
    assert health.retry_after == 100.0 + pool.FIRST_RESTART_DELAY_SECONDS


def test_a_pool_member_without_failures_is_running() -> None:
    """`HEALTHY` — это «жив», а не «упал с неизвестным кодом»."""
    assert pool.HEALTHY.status == "running"


def test_a_process_that_worked_a_while_starts_the_count_over() -> None:
    """Счёт, падающий раз в сутки, не имеет права исчерпать лимит перезапусков за неделю."""
    health = pool.Health(failures=4, last_exit_code=EXIT_ACCOUNT)
    health = pool.after_exit(
        health,
        exit_code=EXIT_ACCOUNT,
        lived_seconds=pool.HEALTHY_UPTIME_SECONDS,
        now=0.0,
    )
    assert health.failures == 1
    assert not health.exhausted


@pytest.mark.parametrize("code", [EXIT_CONFIG, EXIT_PLATFORM])
def test_configuration_and_platform_are_never_retried(code: int) -> None:
    """У нового процесса будут тот же `collector.env` и та же ОС — перезапуск бессмыслен."""
    health = pool.after_exit(pool.HEALTHY, exit_code=code, lived_seconds=0.1, now=0.0)
    assert health.fatal
    assert health.status == "fatal"
    assert not pool.may_start(health, now=1_000_000.0)


def test_clean_exit_is_still_a_failure_for_the_manager() -> None:
    """Процесс счёта не имеет права закончиться сам: менеджер не просил его останавливаться."""
    health = pool.after_exit(pool.HEALTHY, exit_code=EXIT_OK, lived_seconds=0.1, now=0.0)
    assert not health.fatal
    assert health.failures == 1


def test_killed_by_the_system_is_retried() -> None:
    """OOM и `taskkill` дают код, которого нет в наших таблицах, — это падение, не отказ."""
    health = pool.after_exit(pool.HEALTHY, exit_code=-9, lived_seconds=0.1, now=0.0)
    assert not health.fatal
    assert pool.may_start(health, now=1_000_000.0)


def test_fresh_health_may_start_immediately() -> None:
    assert pool.may_start(pool.HEALTHY, now=0.0)


def test_restart_delay_numbering_starts_at_one() -> None:
    with pytest.raises(ValueError):
        pool.restart_delay_seconds(0)
