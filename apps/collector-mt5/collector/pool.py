"""Решения менеджера процессов: кому дать место, кого погасить, кого перезапускать.

Всё в этом модуле — чистые функции и неизменяемые значения. Причина та же, что у
`sync.py`: терминала на машине разработки нет, `multiprocessing` на ней ведёт себя не так,
как на Windows, а проверить надо именно **решения**. Поэтому `main.py` остаётся прослойкой
поверх этого модуля: он умеет запускать и убивать процессы, но не выбирает, кого.

Два правила, ради которых модуль вообще существует отдельно.

**Место, однажды занятое счётом, у него не отнимается.** Пока счёт есть в assignments, он
держит своё место, даже когда его процесс умер и ждёт перезапуска. Иначе четвёртый счёт
занимал бы освободившееся место, первый после перезапуска оказывался бы сверх лимита, и
сообщение «превышен MAX_ACCOUNTS» ходило бы по кругу между счетами — человек читал бы
каждую минуту новую причину, ни одна из которых не была бы правдой.

**Сверх лимита — не молчание, а состояние** (`SPEC.md` §12, `S1-09`). Счёт, которому места
не хватило, возвращается из `plan_slots` поимённо, чтобы менеджеру было о чём послать
heartbeat. Первому пользователю нужно четыре счёта, а значение по умолчанию — три.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Final, Literal

from collector.worker import EXIT_CONFIG, EXIT_PLATFORM

# Сколько раз подряд менеджер поднимает упавший процесс, прежде чем сдаться и сказать об
# этом человеку. Потолок нужен именно потому, что перезапуск дешёвый: без него счёт с
# нечитаемым терминалом крутился бы в петле сутками, оставляя в логе ровно одну строку в
# минуту и ни одного вывода.
MAX_RESTARTS: Final = 5

# Пауза перед перезапуском: удвоение от пяти секунд до пятнадцати минут — та же форма, что
# у ретрая подключения к терминалу (`sync.retry_delay_seconds`). Держится отдельно от неё,
# потому что политика другая: там попытки бесконечны, здесь их считанное число.
FIRST_RESTART_DELAY_SECONDS: Final = 5.0
MAX_RESTART_DELAY_SECONDS: Final = 900.0

# Процесс, проживший столько, считается здоровым: следующая его смерть открывает новый
# счёт падений, а не продолжает старый. Без этого правила счёт, падающий раз в сутки,
# через неделю исчерпал бы лимит перезапусков и остался бы лежать.
HEALTHY_UPTIME_SECONDS: Final = 600.0

# Коды выхода, после которых перезапуск бессмыслен: конфигурация и платформа у нового
# процесса будут те же самые. Всё остальное (включая убийство системой, у которого код
# отрицательный или произвольный) считается падением и перезапускается.
FATAL_EXIT_CODES: Final[frozenset[int]] = frozenset({EXIT_CONFIG, EXIT_PLATFORM})

# Как менеджер видит счёт в момент отчёта. Перечень закрытый: каждое значение обязано
# превращаться во что-то, что человек прочтёт на карточке счёта.
MemberStatus = Literal[
    "running",  # процесс жив
    "restarting",  # процесс умер, менеджер поднимет его снова
    "exhausted",  # перезапуски кончились
    "fatal",  # перезапускать нечего: конфигурация или платформа
]


@dataclass(frozen=True)
class SlotPlan:
    """Раскладка счетов по местам на этом тике.

    Четыре множества, и они не пересекаются: `keep + take` — те, кто работает,
    `over_limit` — те, кому места не хватило, `release` — те, кого пора гасить.
    """

    keep: tuple[str, ...]
    take: tuple[str, ...]
    release: tuple[str, ...]
    over_limit: tuple[str, ...]


def plan_slots(*, held: Sequence[str], assigned: Sequence[str], limit: int) -> SlotPlan:
    """Кого оставить, кого поднять, кого погасить и кто остался без места.

    `held` — счета, за которыми место уже закреплено, в порядке закрепления. `assigned` —
    ответ `GET /internal/collector/assignments`, в порядке сервера (он сортирует по
    `created_at`, то есть первыми идут самые старые счета).

    Приоритет — за теми, кто уже работает: сначала места сохраняются за `held`, и только
    остаток раздаётся новичкам. Так набор счетов в пуле не меняется от того, что сервер
    вернул список в другом порядке, а «кто именно сверх лимита» остаётся одним и тем же
    ответом от тика к тику.
    """
    if limit < 1:
        raise ValueError("MAX_ACCOUNTS не может быть меньше одного")
    assigned_order = _unique(assigned)
    assignable = set(assigned_order)

    still_assigned = [account_id for account_id in _unique(held) if account_id in assignable]
    keep = tuple(still_assigned[:limit])
    # Лимит уменьшили в `collector.env` при живом менеджере — сегодня так случиться не
    # может (настройки читаются один раз при старте), но правило от этого не менее
    # обязательное: лишние места отдаются, а счета уходят в `over_limit`, а не в тишину.
    dropped_by_limit = tuple(still_assigned[limit:])
    release = (
        tuple(account_id for account_id in _unique(held) if account_id not in assignable)
        + dropped_by_limit
    )

    free = limit - len(keep)
    fresh = [account_id for account_id in assigned_order if account_id not in set(still_assigned)]
    take = tuple(fresh[:free]) if free > 0 else ()

    seated = set(keep) | set(take)
    over_limit = tuple(account_id for account_id in assigned_order if account_id not in seated)
    return SlotPlan(keep=keep, take=take, release=release, over_limit=over_limit)


def _unique(values: Iterable[str]) -> list[str]:
    """Порядок сохраняется, повторы выбрасываются: список счетов приходит извне."""
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


@dataclass(frozen=True)
class Health:
    """Что менеджер помнит о падениях процесса одного счёта.

    Значение неизменяемое, переходы — функции ниже. Так «сколько раз мы уже пробовали»
    нельзя случайно потерять или увеличить дважды в разных ветках `main.py`.
    """

    failures: int = 0
    # Перезапускать бессмысленно: у нового процесса будут те же `collector.env` и та же ОС.
    fatal: bool = False
    # Перезапуски кончились. Это не то же самое, что `fatal`: причина неизвестна, и
    # человеку нужен файл лога, а не правка настроек.
    exhausted: bool = False
    last_exit_code: int | None = None
    # Момент по монотонным часам, раньше которого поднимать процесс снова не стоит.
    retry_after: float | None = None

    @property
    def status(self) -> MemberStatus:
        """Как это состояние называется на языке отчёта человеку."""
        if self.fatal:
            return "fatal"
        if self.exhausted:
            return "exhausted"
        return "restarting"


HEALTHY: Final = Health()


def restart_delay_seconds(failures: int) -> float:
    """Пауза перед попыткой №`failures` поднять процесс заново."""
    if failures < 1:
        raise ValueError("попытки нумеруются с единицы")
    return min(FIRST_RESTART_DELAY_SECONDS * 2 ** (failures - 1), MAX_RESTART_DELAY_SECONDS)


def after_exit(
    health: Health,
    *,
    exit_code: int,
    lived_seconds: float,
    now: float,
    max_restarts: int = MAX_RESTARTS,
) -> Health:
    """Новое состояние счёта после смерти его процесса.

    `lived_seconds` не украшение: процесс, проживший рабочий день и упавший один раз, и
    процесс, падающий за секунду при каждом старте, — разные события, и лечатся они
    по-разному. Первый перезапускается молча, второй обязан дойти до человека.
    """
    if exit_code in FATAL_EXIT_CODES:
        return Health(failures=health.failures + 1, fatal=True, last_exit_code=exit_code)
    failures = 1 if lived_seconds >= HEALTHY_UPTIME_SECONDS else health.failures + 1
    if failures > max_restarts:
        return Health(failures=failures, exhausted=True, last_exit_code=exit_code)
    return Health(
        failures=failures,
        last_exit_code=exit_code,
        retry_after=now + restart_delay_seconds(failures),
    )


def may_start(health: Health, *, now: float) -> bool:
    """Пора ли поднимать процесс этого счёта."""
    if health.fatal or health.exhausted:
        return False
    return health.retry_after is None or now >= health.retry_after
