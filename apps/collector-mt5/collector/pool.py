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

**Менеджер говорит только о том, о чём процесс счёта сказать не смог.** `Health.status` —
это решение «что человек прочтёт», и у него есть значение «молчать»: процесс, ушедший с
`EXIT_ACCOUNT`, уже отправил heartbeat с точной причиной, и общий текст менеджера на её
месте — потеря диагноза, а не подстраховка.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from typing import Final, Literal

from collector.worker import EXIT_ACCOUNT, EXIT_CONFIG, EXIT_PLATFORM

# Сколько раз подряд менеджер поднимает упавший процесс, прежде чем сдаться и сказать об
# этом человеку. Потолок нужен именно потому, что перезапуск дешёвый: без него счёт с
# нечитаемым терминалом крутился бы в петле сутками, оставляя в логе ровно одну строку в
# минуту и ни одного вывода.
MAX_RESTARTS: Final = 5

# Пауза перед перезапуском: удвоение от пяти секунд — та же форма, что у ретрая подключения
# к терминалу (`sync.retry_delay_seconds`). Держится отдельно от неё, потому что политика
# другая: там попытки бесконечны, здесь их считанное число.
#
# ⚠️ **При `MAX_RESTARTS=5` потолок недостижим:** используются 5, 10, 20, 40 и 80 секунд, а
# до 900 нужно девять падений подряд. Константа оставлена ограничителем формулы — вырастет
# `MAX_RESTARTS`, и пауза упрётся в него, а не уйдёт в часы, — но политику сегодня описывает
# ряд 5→10→20→40→80, и `SPEC.md` §8.2 говорит именно это.
#
# ⚠️ **Пауза квантуется тиком менеджера.** Перезапуск случается только в `_apply`, то есть
# раз в `HEARTBEAT_INTERVAL_SECONDS`: при значении по умолчанию (60 с) паузы 5, 10, 20 и 40
# неразличимы — процесс, умерший на 60-й секунде, поднимется на 120-й. Ошибки здесь нет,
# но первый же лог с Windows выглядит так, будто пауза не соблюдается.
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

# Коды выхода, означающие «я уже сказал человеку, почему ухожу». Каждый путь `worker.py`,
# возвращающий `EXIT_ACCOUNT`, перед этим шлёт heartbeat `state=error` с точной причиной —
# «счёт не в USD», «батч отвергнут», «задания на счёт нет». Менеджеру после такого добавить
# нечего, а перекрыть он может только точное неточным.
EXPLAINED_EXIT_CODES: Final[frozenset[int]] = frozenset({EXIT_ACCOUNT})

# Как менеджер видит счёт в момент отчёта. Перечень закрытый: каждое значение обязано
# превращаться во что-то, что человек прочтёт на карточке счёта, — либо в решение молчать,
# потому что там уже написано более точное.
MemberStatus = Literal[
    "running",  # процесс жив
    "explained",  # процесс умер, назвав причину сам: она на карточке, трогать её нельзя
    "not_started",  # процесс не запустился вовсе: `spawn` отказал, лога счёта нет
    "restarting",  # процесс умер молча, менеджер поднимет его снова
    "exhausted",  # перезапуски кончились
    "fatal",  # перезапускать нечего: конфигурация или платформа
]


@dataclass(frozen=True)
class SlotPlan:
    """Раскладка счетов по местам на этом тике.

    `keep + take` — те, кто работает; `over_limit` — те, кому места не хватило; `release` —
    те, кого пора гасить. Первые три не пересекаются между собой, и это инвариант.

    ⚠️ `release` пересекается с `over_limit`, и **всегда** — при уменьшении лимита на ходу:
    счёт, у которого место отобрали, обязан и погаснуть, и получить причину. Это не сбой
    раскладки, а два разных вопроса об одном счёте: «гасить ли процесс» и «что написать
    человеку».
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
    остаток раздаётся новичкам. Так «кто именно сверх лимита» остаётся одним и тем же
    ответом от тика к тику, а не переезжает с карточки на карточку.

    ⚠️ Устойчивость к порядку ответа держится **только пока места заняты**. На холодном
    старте `held` пуст, и кто окажется сверх лимита, решает порядок `assigned` целиком. На
    практике его задаёт сервер — `ORDER BY created_at, id`
    (`apps/api/app/domains/collector/service.py`), то есть места достаются самым старым
    счетам, — но это деталь чужого запроса, из коллектора не видимая и ничем здесь не
    закреплённая. Поменяется сортировка на сервере — после перезапуска коллектора без места
    останется другой счёт.
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
    # Процесс ушёл, назвав причину сам (`EXPLAINED_EXIT_CODES`).
    explained: bool = False
    # Процесс не запустился вовсе: `spawn` отказал. Отличается от любого выхода тем, что
    # ни кода, ни файла лога счёта не существует — просить их у человека бессмысленно.
    started: bool = True
    # `None` — кода нет: процесса не было или система не сообщила код.
    last_exit_code: int | None = None
    # Момент по монотонным часам, раньше которого поднимать процесс снова не стоит.
    retry_after: float | None = None

    @property
    def status(self) -> MemberStatus:
        """Как это состояние называется на языке отчёта человеку.

        Порядок ветвлений — это порядок приоритета сообщений, и он выбран так, чтобы более
        точная причина не уступала место менее точной. `explained` идёт впереди
        `exhausted`: после пяти падений причина, которую назвал сам процесс счёта, никуда
        не делась (счёт как был в евро, так и остался), а «пришлите файл лога» на её месте
        — потеря диагноза. `not_started` впереди `exhausted` по той же логике: «кончилась
        память» точнее, чем «падает при каждом запуске».
        """
        if self.failures == 0:
            return "running"
        if self.fatal:
            return "fatal"
        if self.explained:
            return "explained"
        if not self.started:
            return "not_started"
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
    exit_code: int | None,
    lived_seconds: float,
    now: float,
    max_restarts: int = MAX_RESTARTS,
) -> Health:
    """Новое состояние счёта после смерти его процесса.

    `lived_seconds` не украшение: процесс, проживший рабочий день и упавший один раз, и
    процесс, падающий за секунду при каждом старте, — разные события, и лечатся они
    по-разному. Первый перезапускается молча, второй обязан дойти до человека.

    `exit_code=None` — процесс мёртв, а кода система не сообщила. Такое падение считается
    молчаливым: сказать «код 4» вместо неизвестного значило бы утверждать, что процесс
    успел объяснить причину сам.
    """
    explained = exit_code in EXPLAINED_EXIT_CODES
    if exit_code in FATAL_EXIT_CODES:
        return Health(failures=health.failures + 1, fatal=True, last_exit_code=exit_code)
    failures = 1 if lived_seconds >= HEALTHY_UPTIME_SECONDS else health.failures + 1
    if failures > max_restarts:
        return Health(
            failures=failures,
            exhausted=True,
            explained=explained,
            last_exit_code=exit_code,
        )
    return Health(
        failures=failures,
        explained=explained,
        last_exit_code=exit_code,
        retry_after=now + restart_delay_seconds(failures),
    )


def after_failed_start(health: Health, *, now: float, max_restarts: int = MAX_RESTARTS) -> Health:
    """Процесс не удалось даже запустить: `spawn` отказал — память, дескрипторы.

    Считается падением (место за счётом, попытка засчитана, следующая через паузу), но не
    выходом: кода выхода нет и файла `account-<id>.log` нет — процесс до логирования не
    дошёл. Человеку поэтому нужен свой текст, а не «пришлите лог счёта».
    """
    after = after_exit(
        health, exit_code=None, lived_seconds=0.0, now=now, max_restarts=max_restarts
    )
    return replace(after, started=False)


def may_start(health: Health, *, now: float) -> bool:
    """Пора ли поднимать процесс этого счёта."""
    if health.fatal or health.exhausted:
        return False
    return health.retry_after is None or now >= health.retry_after
