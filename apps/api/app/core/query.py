"""Повторённый query-параметр — ошибка, а не «побеждает последний».

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

from fastapi import Request

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
