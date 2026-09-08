"""Пересчёт `daily_stats` — задача `refresh_daily_stats` из SPEC.md 10.

**Таблица — кэш, а не источник** (`docs/metrics.md` §6): календарь и сводка считают по
`positions`, поэтому устаревшую строку человек не увидит никогда. Отсюда и устройство
задачи: она не «досчитывает разницу», а сносит затронутые дни и собирает их заново из
источника. Пересчёт идемпотентен, дважды запущенный даёт то же самое, и любой сбой
лечится повторным запуском, а не разбором того, что успело записаться.

Без аргументов — «пересчитать все дни счёта», и это всегда безопасный вариант: один проход
по позициям счёта. Сузить его можно двумя способами, и оба для того, кто точно знает, что
тронул.

* `within` — **отрезок UTC**, за пределами которого суточная агрегация измениться не могла.
  Так зовёт `POST /ingest/deals` (`S1-04`): дни он посчитать не может — день режется по
  зоне и границе дня **владельца** счёта (§6 `docs/metrics.md`), а ингест приходит по
  сервисному токену установки и владельца не видит. Правило дня остаётся здесь, в одном
  месте, а звонящий отдаёт только моменты времени.
* `days` — готовый список дней, для звонящего, который правило дня уже применил.

Диапазон дней в режимах «все» и `within` берётся с запасом в двое суток вокруг крайних
моментов: день пользователя сдвинут относительно UTC на смещение зоны (до ±14 часов) плюс
границу дня (до 23 часов). Запас может дать лишние пустые дни — они просто не породят
строк; нехватка запаса потеряла бы день целиком, поэтому ошибка выбрана в безопасную
сторону.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, bindparam, delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.accounts import models as account_models
from app.domains.analytics import models
from app.domains.analytics.trading_day import DAY_RANGE_MARGIN_DAYS, DAYS_CTE
from app.domains.auth import models as auth_models
from app.domains.ingest import models as ingest_models
from app.domains.journal.service import STATUS_CLOSED

_DAY_FILTER = "and days.day in :days"

# `volume` — объём закрытых позиций дня. У закрытой позиции объём входа равен объёму
# выхода (SPEC.md 7), поэтому какой из двух брать — вопрос вкуса, а не расчёта.
_INSERT_SQL = """
with {days_cte}
insert into daily_stats (
    account_id, day, trades, wins, losses, breakeven,
    gross_pnl, net_pnl, commission, swap, fee, volume,
    timezone, day_boundary_hour, computed_at
)
select
    :account_id,
    days.day,
    count(*),
    count(*) filter (where p.net_pnl > 0),
    count(*) filter (where p.net_pnl < 0),
    count(*) filter (where p.net_pnl = 0),
    sum(p.gross_pnl),
    sum(p.net_pnl),
    sum(p.commission),
    sum(p.swap),
    sum(p.fee),
    sum(p.volume_closed),
    :timezone,
    :day_boundary_hour,
    now()
from days
join positions p
  on p.close_time >= days.starts_at
 and p.close_time < days.ends_at
where p.account_id = :account_id
  and p.status = :closed_status
  {day_filter}
group by days.day
"""


async def refresh(
    session: AsyncSession,
    account_id: UUID,
    days: Sequence[date] | None = None,
    *,
    within: tuple[datetime, datetime] | None = None,
) -> int:
    """Пересчитывает дни счёта. Возвращает число записанных строк.

    Счёт, которого уже нет, — не ошибка: задача могла встать в очередь до удаления счёта,
    и падать на этом означало бы держать в очереди вечно неудачную работу.
    """
    if days is not None and within is not None:
        raise ValueError("refresh принимает либо список дней, либо отрезок времени")

    settings = await _account_day_settings(session, account_id)
    if settings is None:
        return 0
    timezone, day_boundary_hour = settings

    requested = sorted(set(days)) if days is not None else None
    if requested is not None and not requested:
        return 0

    margin = timedelta(days=DAY_RANGE_MARGIN_DAYS)
    window = None if within is None else (within[0].date() - margin, within[1].date() + margin)
    await _delete_days(session, account_id, requested, window)

    if requested is not None:
        first_day, last_day = requested[0], requested[-1]
    elif window is not None:
        first_day, last_day = window
    else:
        span = await _closed_span(session, account_id)
        if span is None:
            await session.commit()
            return 0
        first_day, last_day = span[0] - margin, span[1] + margin

    statement = text(
        _INSERT_SQL.format(
            days_cte=DAYS_CTE, day_filter=_DAY_FILTER if requested is not None else ""
        )
    )
    params = {
        "account_id": account_id,
        "timezone": timezone,
        "day_boundary_hour": day_boundary_hour,
        "first_day": first_day,
        "last_day": last_day,
        "closed_status": STATUS_CLOSED,
    }
    if requested is not None:
        statement = statement.bindparams(bindparam("days", expanding=True))
        params["days"] = requested

    result = await session.execute(statement, params)
    await session.commit()
    # INSERT всегда возвращает CursorResult, но типы SQLAlchemy обещают только Result.
    return cast(CursorResult[Any], result).rowcount


async def _account_day_settings(session: AsyncSession, account_id: UUID) -> tuple[str, int] | None:
    """Зона и граница дня владельца счёта — правило, по которому режется день."""
    statement = (
        select(auth_models.User.timezone, auth_models.User.day_boundary_hour)
        .join(
            account_models.TradingAccount,
            account_models.TradingAccount.user_id == auth_models.User.id,
        )
        .where(account_models.TradingAccount.id == account_id)
    )
    row = (await session.execute(statement)).one_or_none()
    return None if row is None else (row.timezone, row.day_boundary_hour)


async def _closed_span(session: AsyncSession, account_id: UUID) -> tuple[date, date] | None:
    """Крайние даты закрытий счёта в UTC — грубая рамка для генерации дней, не сам день."""
    position = ingest_models.Position
    statement = select(func.min(position.close_time), func.max(position.close_time)).where(
        position.account_id == account_id, position.status == STATUS_CLOSED
    )
    first, last = (await session.execute(statement)).one()
    if first is None or last is None:
        return None
    return first.date(), last.date()


async def _delete_days(
    session: AsyncSession,
    account_id: UUID,
    days: Sequence[date] | None,
    window: tuple[date, date] | None,
) -> None:
    """Сносит то, что сейчас будет собрано заново. Без сужения — весь кэш счёта."""
    statement = delete(models.DailyStat).where(models.DailyStat.account_id == account_id)
    if days is not None:
        statement = statement.where(models.DailyStat.day.in_(list(days)))
    elif window is not None:
        statement = statement.where(models.DailyStat.day.between(*window))
    await session.execute(statement)
