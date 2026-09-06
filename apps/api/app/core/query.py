"""Общие правила параметров запроса: повтор ключа и фильтры «счета + период».

Две части. Первая — зависимость `reject_repeated_query_params`. Вторая — базовые модели
фильтров (`AccountScopedQuery`, `PeriodQuery`), от которых наследуются фильтры доменов.

Базовые модели живут здесь, а не в домене, который первым их написал: `?account_ids=` и
`?from=&to=` есть у списка журнала (SPEC.md 5.4), у сводки и у календаря (5.5), и это
обязано быть **одно** правило. Две копии разъезжаются молча — сводка и список показали бы
разные множества строк за один и тот же период, и заметить это можно было бы только сложив
колонку на экране вручную.

**Повторённый query-параметр — ошибка, а не «побеждает последний».**

`?account_ids=A&account_ids=B` доезжает до скалярного поля модели как одно значение `B`:
Starlette кладёт в `query_params` последнее, первое исчезает без слова, и ответ приходит
`200 OK` с выборкой по одному счёту из двух. Так ведёт себя любой скалярный фильтр.

Попасть сюда клиенту легко и без ошибки в коде: `URLSearchParams.append` и `qs` в режиме
`repeat` сериализуют массив именно повтором ключа — это способ по умолчанию у половины
HTTP-клиентов. То есть «выбрал два счёта в переключателе» превращается в «увидел один» на
первом же наивном клиенте.

Молча терять фильтр нельзя ровно по той же причине, по которой список фильтров закрыт
(`extra="forbid"` в `PositionsQuery`), а чужой `account_id` роняет весь запрос вместо того,
чтобы выпасть из выборки: неполная выборка, которую человек читает как полную, хуже 400.
Все три правила — одно решение, и держаться они должны вместе.

Проверка стоит отдельной зависимостью маршрута, а не в модели: pydantic получает от FastAPI
уже схлопнутое значение и повтора не видит. Ошибка — обычный `400 validation_error` с
`details.fields` (SPEC.md 5.1), потому что это ошибка параметра запроса и ничего больше.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from uuid import UUID

from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from app.core.errors import CODE_BY_STATUS, MESSAGE_BY_STATUS, ApiError

QUERY_LOCATION = "query"

REPEATED_PARAM_ERROR = (
    "Параметр указан несколько раз. Повторы не объединяются — оставьте один параметр, "
    "список значений задаётся в нём через запятую"
)


async def reject_repeated_query_params(request: Request) -> None:
    """Зависимость маршрута: повтор любого параметра в строке запроса — 400.

    Перечисляются все повторённые ключи сразу, а не первый попавшийся: клиент, который
    сериализует массивы повтором, прислал так все свои списки, и чинить их по одному он
    будет столько же раз, сколько у него фильтров.
    """
    counts = Counter(key for key, _ in request.query_params.multi_items())
    repeated = sorted(key for key, count in counts.items() if count > 1)
    if not repeated:
        return
    raise ApiError(
        CODE_BY_STATUS[400],
        MESSAGE_BY_STATUS[400],
        status_code=400,
        details={"fields": {f"{QUERY_LOCATION}.{key}": REPEATED_PARAM_ERROR for key in repeated}},
    )


FILTER_SEPARATOR = ","

MAX_ACCOUNT_IDS = 100

ACCOUNT_IDS_ERROR = "account_ids — список UUID через запятую"
TOO_MANY_ACCOUNT_IDS_ERROR = f"Не больше {MAX_ACCOUNT_IDS} счетов в фильтре"
NAIVE_DATETIME_ERROR = (
    "Укажите время с часовым поясом, например 2026-09-01T00:00:00Z: "
    "без него непонятно, чей это день"
)
RANGE_ERROR = "Начало периода должно быть раньше конца"

ACCOUNT_IDS_DESCRIPTION = "UUID счетов через запятую. Пусто — все неархивированные счета"
FROM_DESCRIPTION = (
    "Начало периода включительно. Сравнивается с временем закрытия, "
    "а у ещё открытых позиций — с временем открытия"
)
TO_DESCRIPTION = "Конец периода, не включая границу"


def split_filter(raw: str | None) -> list[str]:
    if raw is None:
        return []
    return [part.strip() for part in raw.split(FILTER_SEPARATOR) if part.strip()]


class AccountScopedQuery(BaseModel):
    """Фильтр по счетам — SPEC.md 5.1: «пусто = все не архивированные счета пользователя».

    `extra="forbid"` наследуется всеми потомками намеренно: опечатка в имени параметра
    (`symbols` вместо `symbol`) иначе молча вернула бы нефильтрованный ответ, и человек
    принял бы чужие строки за свои. Лучше 400.
    """

    model_config = ConfigDict(extra="forbid")

    account_ids: str | None = Field(default=None, description=ACCOUNT_IDS_DESCRIPTION)

    @field_validator("account_ids")
    @classmethod
    def _account_ids(cls, value: str | None) -> str | None:
        """Разбор здесь, а не в свойстве: только на границе он даёт 400, а не 500."""
        parts = split_filter(value)
        if len(parts) > MAX_ACCOUNT_IDS:
            raise PydanticCustomError("account_ids", TOO_MANY_ACCOUNT_IDS_ERROR)
        for part in parts:
            try:
                UUID(part)
            except ValueError as error:
                raise PydanticCustomError("account_ids", ACCOUNT_IDS_ERROR) from error
        return value

    @property
    def account_id_list(self) -> list[UUID]:
        """Пусто — «все неархивированные счета» (SPEC.md 5.1)."""
        return [UUID(part) for part in split_filter(self.account_ids)]


class PeriodQuery(AccountScopedQuery):
    """Счета плюс период. Границы — моменты, а не даты: чей это день, знает только клиент."""

    date_from: datetime | None = Field(default=None, alias="from", description=FROM_DESCRIPTION)
    date_to: datetime | None = Field(default=None, alias="to", description=TO_DESCRIPTION)

    @field_validator("date_from", "date_to")
    @classmethod
    def _requires_offset(cls, value: datetime | None) -> datetime | None:
        """Наивное время — не «UTC по умолчанию», а незаданный вопрос.

        Приняв его молча, мы сдвинули бы границу периода на смещение пользователя и
        выкинули из выборки сделки его вечера.
        """
        if value is not None and value.tzinfo is None:
            raise PydanticCustomError("naive_datetime", NAIVE_DATETIME_ERROR)
        return value

    @model_validator(mode="after")
    def _range_is_not_empty(self) -> PeriodQuery:
        """Перевёрнутый период — ошибка, а не пустой ответ.

        Пустой список в ответ на `from > to` человек читает как «сделок нет», а не как
        «границы перепутаны», и ищет пропажу в данных.
        """
        if (
            self.date_from is not None
            and self.date_to is not None
            and self.date_from >= self.date_to
        ):
            raise PydanticCustomError("range", RANGE_ERROR)
        return self
