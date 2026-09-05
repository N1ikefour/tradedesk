"""Строки таблицы `symbols`: словарь инструментов, общий на всю установку (SPEC.md 6.4).

Разбор имени — `symbols.py`, чистый и без БД. Здесь единственное, ради чего нужна БД:
символ заводится **при первом появлении** и после этого не меняется автоматикой.

Два правила, и оба про то, чего этот модуль не делает.

1. **Существующая строка не переписывается никогда.** SPEC.md 6.4 требует этого для
   `source='user'`: человек однажды поправил имя через UI (этап 4), и следующий синк не
   вправе вернуть машинное значение — иначе правка выглядит несохранившейся. В v1 правило
   шире буквы спеки: не переписывается ни одна строка, включая `auto`. Так идемпотентность
   синка (второй батч с тем же символом не меняет ничего) не зависит от значения колонки
   `source`, которую сегодня некому заполнить, а `UPDATE` в этом модуле просто отсутствует
   как код. Цена решения названа: улучшение seed-словаря не доедет до символов, заведённых
   до улучшения, — это разовый backfill отдельной задачей, а не побочный эффект синка.
2. **Символ не привязан к счёту и к пользователю** — так описана таблица в SPEC.md 3.3:
   `raw` уникален глобально. Отсюда следствие, которого в спеке нет: ручная правка
   `EURUSD.m` видна на всех счетах всех пользователей установки. Для v1 (одна установка —
   один трейдер) это то, что нужно; для многопользовательской — нет.

Дедупликация — не «уже есть → ошибка», а `ON CONFLICT DO NOTHING`: перекрывающиеся батчи
у нас норма (коллектор намеренно перезапрашивает окно), и два параллельных синка разных
счетов легко приносят один и тот же символ.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domains.ingest.models import Symbol
from app.domains.ingest.symbols import UNKNOWN_ASSET_CLASS, resolve_symbol

log = get_logger(__name__)

# Значения колонки `symbols.source` (SPEC.md 3.3).
SOURCE_AUTO = "auto"
SOURCE_USER = "user"
# 'seed' в v1 не пишется никем: словарь известных символов живёт кодом (`KNOWN_SYMBOLS`),
# а не строками таблицы. Строка со `raw='EURUSD'` утверждала бы, что такой символ у брокера
# есть, — а у брокера с суффиксами его нет.
SOURCE_SEED = "seed"


@dataclass(frozen=True, slots=True)
class RegisteredSymbol:
    """Строка `symbols` в том виде, в каком её видит ингест. `norm` — то, что лежит в БД.

    Именно то, а не пересчитанное: если человек поправил имя руками, позиции обязаны
    собираться под его именем, а не под машинным.
    """

    raw: str
    norm: str
    asset_class: str | None
    source: str


async def ensure_symbols(
    session: AsyncSession, raw_symbols: Iterable[str]
) -> dict[str, RegisteredSymbol]:
    """Строки `symbols` для символов батча: недостающие заводятся, существующие читаются.

    Возвращает отображение сырого символа в строку словаря — из него S1-04 берёт
    `positions.symbol_norm`. Транзакцией управляет вызывающий: здесь нет ни commit,
    ни rollback, потому что символы заводятся в той же транзакции, что и сделки.
    """
    wanted = sorted(set(raw_symbols))
    if not wanted:
        return {}

    known = await _load(session, wanted)
    missing = [raw for raw in wanted if raw not in known]
    if not missing:
        return known

    inserted = await session.execute(
        pg_insert(Symbol)
        .values(
            [
                {
                    "raw": item.raw,
                    "norm": item.norm,
                    "asset_class": item.asset_class,
                    "source": SOURCE_AUTO,
                }
                for item in (resolve_symbol(raw) for raw in missing)
            ]
        )
        .on_conflict_do_nothing(index_elements=[Symbol.raw])
        .returning(Symbol.raw)
    )
    # RETURNING при DO NOTHING отдаёт только реально вставленные строки, поэтому `created`
    # ниже — число, а не намерение: под гонкой часть строк создаёт не этот синк.
    created = set(inserted.scalars())
    # Перечитывается всё, чего не было при чтении, а не только созданное: при гонке
    # победила чужая строка, и дальше работать надо с ней. Своё разрешённое имя в ответ
    # подставлять нельзя — оно уже не то, что в БД, а позиции собираются по тому, что в БД.
    known.update(await _load(session, missing))

    log.info(
        "symbols.registered",
        requested=len(wanted),
        created=len(created),
        # Сами символы в лог не идут: это внешний текст, а `^\S+$` на границе (S1-01)
        # пропускает и управляющие байты. Строка таблицы их и так хранит и запрашивается.
        # Счётчик нераспознанных — рабочий сигнал по допущению 12: словарь суффиксов
        # составлен не по данным, и рост этого числа означает, что он мимо брокера.
        unclassified=sum(1 for raw in created if known[raw].asset_class == UNKNOWN_ASSET_CLASS),
    )
    return known


async def _load(session: AsyncSession, raws: Sequence[str]) -> dict[str, RegisteredSymbol]:
    """Порядок `raws` отсортирован вызывающим: одинаковый порядок блокировок у всех синков."""
    rows = await session.execute(
        select(Symbol.raw, Symbol.norm, Symbol.asset_class, Symbol.source).where(
            Symbol.raw.in_(raws)
        )
    )
    return {
        raw: RegisteredSymbol(raw=raw, norm=norm, asset_class=asset_class, source=source)
        for raw, norm, asset_class, source in rows.all()
    }
