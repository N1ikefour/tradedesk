"""Формат ошибок в OpenAPI — ADR-0004.

SPEC.md 5.1 задаёт один формат ошибки на весь API, поэтому он объявляется здесь один
раз для всех операций, а не повторяется в `responses=` каждого маршрута: забытый
`responses=` вернул бы расхождение молча, и заметить его можно было бы только на фронте.

Заодно снимается автоматический `422 HTTPValidationError` от FastAPI — приложение его
никогда не отдаёт: `validation_error_handler` приводит такую ошибку к `400
validation_error`.

Маршрут добавляет `responses=domain_errors(...)` только там, где производит собственный
код поверх общего набора.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from copy import deepcopy
from typing import Any

from fastapi import FastAPI

from app.core.errors import CODE_BY_STATUS, MESSAGE_BY_STATUS
from app.core.origin import FORBIDDEN_ORIGIN_CODE

JSON_MEDIA_TYPE = "application/json"

ERROR_SCHEMA_NAME = "ApiError"
ERROR_CODE_SCHEMA_NAME = "ErrorCode"
ERROR_CODE_REF = f"#/components/schemas/{ERROR_CODE_SCHEMA_NAME}"

# FastAPI объявляет их только ради автоматического 422, который здесь снимается.
GENERATED_VALIDATION_SCHEMAS = ("HTTPValidationError", "ValidationError")
GENERATED_VALIDATION_REF = "#/components/schemas/HTTPValidationError"

HTTP_METHODS = frozenset({"get", "put", "post", "delete", "options", "head", "patch", "trace"})

# Общий набор: словарь SPEC.md 5.1 плюс то, что порождает не домен, а окружение —
# 405 от роутера и 500 от общего обработчика (S0-02), `forbidden_origin` от проверки
# Origin (SPEC.md 4): это middleware, она стоит перед любым мутирующим маршрутом,
# поэтому её код общий, а не эндпоинтный.
# Часть кодов объявлена авансом, производителя у них пока нет: 409 и 415 (появится
# в S2-04 — неподходящий тип файла при загрузке вложений). Ни FastAPI 0.141, ни
# Starlette 415 не ставят: неподходящий Content-Type они приводят к ошибке валидации,
# то есть к нашему 400. По ADR-0004 такие коды объявляются заранее — фронт должен уметь
# их обрабатывать до появления производителя.
#
# 413 `payload_too_large` требует SPEC.md 5.3 (батч длиннее 5000 сделок) и производит
# ещё потолок на размер тела (`core/body_limit.py`). В перечне §5.1 его нет — как нет
# там и 405, — поэтому он живёт здесь по тому же правилу: код, который фронт увидит,
# обязан быть в схеме. Общий, а не эндпоинтный, как и 429: у того производитель тоже
# ровно один маршрут, а объявлен он на всех.
GLOBAL_ERROR_CODES: Mapping[int, tuple[str, ...]] = {
    400: (CODE_BY_STATUS[400],),
    401: (CODE_BY_STATUS[401],),
    403: (CODE_BY_STATUS[403], FORBIDDEN_ORIGIN_CODE),
    404: (CODE_BY_STATUS[404],),
    405: (CODE_BY_STATUS[405],),
    409: (CODE_BY_STATUS[409],),
    413: (CODE_BY_STATUS[413],),
    415: (CODE_BY_STATUS[415],),
    422: (CODE_BY_STATUS[422],),
    429: (CODE_BY_STATUS[429],),
    500: (CODE_BY_STATUS[500],),
}


ANY_DETAILS: dict[str, Any] = {"type": "object", "additionalProperties": True}

# SPEC.md 5.1 связывает `validation_error` с `details.fields`, и `validation_error_handler`
# заполняет его на любом маршруте — поэтому форма описана в общем наборе.
VALIDATION_DETAILS: dict[str, Any] = {
    "type": "object",
    "required": ["fields"],
    "properties": {"fields": {"type": "object", "additionalProperties": {"type": "string"}}},
}

# SPEC.md 5.1: «При превышении — 429 с retry_after». Производитель один (лимиты
# `/auth/request-code`), поэтому форма объявляется на маршруте, а не в общем наборе.
RETRY_AFTER_DETAILS: dict[str, Any] = {
    "type": "object",
    "required": ["retry_after"],
    "properties": {
        "retry_after": {"type": "integer", "description": "Секунд до следующей попытки"}
    },
}

# `unhandled_exception_handler` наружу отдаёт только код и общее сообщение: текст
# исключения может нести секреты (S0-04), поэтому `details` у 500 всегда пуст.
EMPTY_DETAILS: dict[str, Any] = {"type": "object", "additionalProperties": False}

GLOBAL_DETAILS: Mapping[int, dict[str, Any]] = {400: VALIDATION_DETAILS, 500: EMPTY_DETAILS}


def error_body_schema(
    codes: Sequence[str], details: Mapping[str, Any] = ANY_DETAILS
) -> dict[str, Any]:
    """Тело ошибки с `code`, суженным до кодов, возможных на этом ответе."""
    return {
        "type": "object",
        "required": ["error"],
        # Конверт закрыт на обоих уровнях: `error_payload` кладёт ровно эти поля и ничего
        # сверх. Открытый объект пропустил бы наружу лишнее — например, стек.
        "additionalProperties": False,
        "properties": {
            "error": {
                "type": "object",
                "required": ["code", "message", "details"],
                "additionalProperties": False,
                "properties": {
                    "code": {"type": "string", "enum": sorted(set(codes))},
                    "message": {"type": "string"},
                    # Глубокая копия: объявления делят константы `*_DETAILS`, и правка
                    # вложенного `properties` в одном месте разошлась бы по всем.
                    "details": deepcopy(dict(details)),
                },
            }
        },
    }


def error_response_spec(
    status_code: int, codes: Sequence[str], details: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    listed = ", ".join(sorted(set(codes)))
    body = error_body_schema(codes, details or GLOBAL_DETAILS.get(status_code, ANY_DETAILS))
    return {
        "description": f"{MESSAGE_BY_STATUS[status_code]} ({listed})",
        "content": {JSON_MEDIA_TYPE: {"schema": body}},
    }


def domain_errors(
    codes_by_status: Mapping[int, Sequence[str]],
    details_by_status: Mapping[int, Mapping[str, Any]] | None = None,
) -> dict[int | str, dict[str, Any]]:
    """`responses=` маршрута, который производит собственные коды поверх общего набора.

    Общий код статуса добавляется сам: объявление маршрута заменяет общее целиком,
    и без этого `unprocessable_entity` пропал бы там, где появился `invalid_code`.
    """
    details = details_by_status or {}
    return {
        status_code: error_response_spec(
            status_code, (*GLOBAL_ERROR_CODES[status_code], *codes), details.get(status_code)
        )
        for status_code, codes in codes_by_status.items()
    }


def install_error_responses(app: FastAPI) -> None:
    """Дополняет схему приложения объявлением ошибок. Схема считается лениво, один раз."""
    generate = app.openapi

    def openapi() -> dict[str, Any]:
        schema = app.openapi_schema
        if schema is None:
            schema = describe_errors(generate())
            app.openapi_schema = schema
        return schema

    app.openapi = openapi  # type: ignore[method-assign]


def describe_errors(schema: dict[str, Any]) -> dict[str, Any]:
    """Правит готовую схему на месте: общие ответы на каждую операцию, словарь кодов."""
    declared: set[str] = set()
    for operation in operations(schema):
        responses = operation.setdefault("responses", {})
        _drop_generated_validation_response(responses)
        for status_code, codes in GLOBAL_ERROR_CODES.items():
            responses.setdefault(str(status_code), error_response_spec(status_code, codes))
        declared |= declared_codes(responses)

    components: dict[str, Any] = schema.setdefault("components", {}).setdefault("schemas", {})
    for name in GENERATED_VALIDATION_SCHEMAS:
        components.pop(name, None)
    components[ERROR_CODE_SCHEMA_NAME] = {
        "title": ERROR_CODE_SCHEMA_NAME,
        "description": "Словарь кодов ошибок API — SPEC.md 5.1.",
        "type": "string",
        "enum": sorted(declared),
    }
    # Ни один ответ на него не ссылается — у ответов `code` сужен до своих кодов.
    # Модель нужна фронту: общий разбор ошибки пишется по одному типу, а не по объединению
    # инлайновых схем всех операций.
    components[ERROR_SCHEMA_NAME] = {
        "title": ERROR_SCHEMA_NAME,
        "description": "Формат ошибки SPEC.md 5.1 — тело любого ответа с ошибкой.",
        "type": "object",
        "required": ["error"],
        "additionalProperties": False,
        "properties": {
            "error": {
                "type": "object",
                "required": ["code", "message", "details"],
                "additionalProperties": False,
                "properties": {
                    "code": {"$ref": ERROR_CODE_REF},
                    "message": {"type": "string"},
                    "details": {"type": "object", "additionalProperties": True},
                },
            }
        },
    }
    return schema


def operations(schema: Mapping[str, Any]) -> Iterator[dict[str, Any]]:
    """Только операции: в path item лежат ещё `parameters`, `summary` и прочее."""
    for path_item in schema.get("paths", {}).values():
        for method, operation in path_item.items():
            if method in HTTP_METHODS and isinstance(operation, dict):
                yield operation


def declared_codes(responses: Mapping[str, Any]) -> set[str]:
    """Коды, объявленные ответами операции. Успешные ответы под форму не подходят."""
    found: set[str] = set()
    for response in responses.values():
        code = (
            _response_schema(response)
            .get("properties", {})
            .get("error", {})
            .get("properties", {})
            .get("code", {})
        )
        found |= set(code.get("enum", ()))
    return found


def _response_schema(response: Any) -> dict[str, Any]:
    if not isinstance(response, dict):
        return {}
    schema = response.get("content", {}).get(JSON_MEDIA_TYPE, {}).get("schema", {})
    return schema if isinstance(schema, dict) else {}


def _drop_generated_validation_response(responses: dict[str, Any]) -> None:
    """Снимает только автоматический 422 FastAPI — по ссылке на его модель."""
    if _response_schema(responses.get("422")).get("$ref") == GENERATED_VALIDATION_REF:
        del responses["422"]
