"""Словари рефлексии — SPEC.md 3.5.

Отдаются фронту как есть (`GET /api/v1/journal/vocab`), русские подписи живут в
`apps/web/src/i18n/ru.ts`. **Ключи стабильны и не переименовываются**: они лежат в
`reflections.emotion_*` и `reflections.mistakes` уже сохранёнными, и переименование ключа
превратило бы прошлые рефлексии в записи, для которых у фронта нет подписи, а у фильтров —
значения. Добавлять в конец можно, менять и удалять — нет.

Значения объявлены `Literal`, а кортежи выводятся из них `get_args`, а не наоборот и не
двумя списками. Это даёт три вещи из одного объявления: проверку тела запроса pydantic'ом,
перечисление в OpenAPI (то есть типы фронта из `make types`) и тело `/journal/vocab`.
Два независимых списка разъехались бы молча — приняли бы значение, которого нет в меню.
"""

from __future__ import annotations

from typing import Literal, get_args

Emotion = Literal[
    "calm",
    "focused",
    "edgy",
    "fomo",
    "frustrated",
    "bored",
    "euphoric",
    "fearful",
    "tired",
]

Mistake = Literal[
    "no_plan",
    "early_entry",
    "late_entry",
    "chased",
    "moved_sl",
    "no_sl",
    "oversized",
    "revenge",
    "early_exit",
    "held_too_long",
    "against_trend",
    "news_ignored",
    "overtrading",
]

# Оценки живут здесь, а не в schemas.py, по той же причине, что и остальные словари:
# их же значения стоят в `check` таблицы `reflections` (SPEC.md 3.4).
Grade = Literal["A", "B", "C", "D"]

EMOTIONS: tuple[str, ...] = get_args(Emotion)
MISTAKES: tuple[str, ...] = get_args(Mistake)
SETUP_GRADES: tuple[str, ...] = get_args(Grade)
EXECUTION_GRADES: tuple[str, ...] = SETUP_GRADES

# Границы `confidence` (SPEC.md 3.4, `check (confidence between 1 and 5)`). В словарь,
# который отдаётся фронту, не входят: SPEC.md 3.5 перечисляет наборы значений, а это
# диапазон, и место ему рядом с проверкой тела запроса.
CONFIDENCE_MIN = 1
CONFIDENCE_MAX = 5
