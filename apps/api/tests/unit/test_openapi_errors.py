"""Ошибки в OpenAPI — ADR-0004.

Главное здесь — сверка: тело, которое приложение действительно отдаёт, проверяется
против схемы, объявленной для этой же операции. Глазами такое расхождение не ловится,
а фронт генерирует типы из схемы (`make types`), и врущая схема уезжает во все фичи.

Схема разбирается «руками», без jsonschema: зависимость в SPEC.md 2.3 не разрешена,
а поддержать нужно ровно то, что мы объявляем — $ref, type, required, properties,
additionalProperties, enum.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response

from app.core.errors import register_error_handlers
from app.core.openapi import ERROR_CODE_SCHEMA_NAME, ERROR_SCHEMA_NAME, JSON_MEDIA_TYPE

API = "/api/v1"

# Словарь SPEC.md 5.1 плюс то, что порождает не домен, а окружение: 405/415 от фреймворка
# (S0-02) и forbidden_origin от проверки Origin (SPEC.md 4). Набор продублирован здесь
# намеренно: тест сверяет схему со спекой, а не с таблицей, из которой схема построена.
EXPECTED_GLOBAL_CODES: dict[int, set[str]] = {
    400: {"validation_error"},
    401: {"unauthorized"},
    403: {"forbidden", "forbidden_origin"},
    404: {"not_found"},
    405: {"method_not_allowed"},
    409: {"conflict"},
    415: {"unsupported_media_type"},
    422: {"unprocessable_entity"},
    429: {"rate_limited"},
    500: {"internal_error"},
}

# Доменные коды — поверх общего набора, на своих маршрутах (ADR-0004).
EXPECTED_DOMAIN_CODES: dict[tuple[str, str, int], set[str]] = {
    (f"{API}/auth/verify", "post", 422): {"invalid_code", "too_many_attempts"},
    (f"{API}/auth/request-code", "post", 429): {"rate_limited"},
}


@pytest.fixture
def app(unreachable_env: pytest.MonkeyPatch, make_app: Callable[[], FastAPI]) -> FastAPI:
    """Зависимости смотрят в закрытый порт: до них ошибка валидации не доходит.

    Импорт `app.main` — внутри фабрики `make_app` (X-09): на уровне модуля он собрал бы
    приложение с настройками из .env раньше, чем фикстуры их подменят.
    """
    return make_app()


@pytest.fixture
def document(app: FastAPI) -> dict[str, Any]:
    return app.openapi()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _operations(document: dict[str, Any]) -> Iterator[tuple[str, str, dict[str, Any]]]:
    for path, item in document["paths"].items():
        for method, operation in item.items():
            if isinstance(operation, dict) and "responses" in operation:
                yield path, method, operation


def _declared(document: dict[str, Any], path: str, method: str, status_code: int) -> dict[str, Any]:
    responses = document["paths"][path][method]["responses"]
    declared = responses.get(str(status_code))
    assert declared is not None, (
        f"{method.upper()} {path}: ответ {status_code} в схеме не объявлен, "
        f"объявлены {sorted(responses)}"
    )
    assert isinstance(declared, dict)
    return declared


def _code_enum(declared: dict[str, Any]) -> set[str]:
    schema = declared["content"][JSON_MEDIA_TYPE]["schema"]
    return set(schema["properties"]["error"]["properties"]["code"]["enum"])


def _resolve(document: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    for _ in range(10):
        reference = node.get("$ref")
        if reference is None:
            return node
        target: Any = document
        for part in reference.removeprefix("#/").split("/"):
            assert isinstance(target, dict) and part in target, (
                f"ссылка не разрешается: {reference}"
            )
            target = target[part]
        node = target
    raise AssertionError(f"ссылки зациклены: {node}")


def assert_matches(document: dict[str, Any], node: dict[str, Any], value: Any, where: str) -> None:
    node = _resolve(document, node)
    kind = node.get("type")
    if kind == "object":
        assert isinstance(value, dict), f"{where}: ожидался объект, получено {type(value).__name__}"
        for name in node.get("required", ()):
            assert name in value, f"{where}: нет обязательного поля {name!r}"
        properties = node.get("properties", {})
        additional = node.get("additionalProperties", True)
        for name, item in value.items():
            if name in properties:
                assert_matches(document, properties[name], item, f"{where}.{name}")
            elif isinstance(additional, dict):
                assert_matches(document, additional, item, f"{where}.{name}")
            else:
                assert additional is not False, f"{where}: поле {name!r} схемой не разрешено"
    elif kind == "string":
        assert isinstance(value, str), f"{where}: ожидалась строка, получено {value!r}"
    elif kind == "integer":
        assert isinstance(value, int), f"{where}: ожидалось целое, получено {value!r}"
    if "enum" in node:
        assert value in node["enum"], f"{where}: {value!r} не объявлен, объявлены {node['enum']}"


def assert_response_matches_schema(
    document: dict[str, Any], method: str, path: str, response: Response
) -> None:
    """Фактический ответ — против схемы, объявленной ровно для этой операции и кода."""
    declared = _declared(document, path, method, response.status_code)
    schema = declared["content"][JSON_MEDIA_TYPE]["schema"]
    assert_matches(
        document, schema, response.json(), f"{method.upper()} {path} {response.status_code}"
    )


def assert_declaration_is_global(document: dict[str, Any], status_code: int) -> dict[str, Any]:
    """Объявление статуса, общее для всех операций; заодно проверяет, что оно одно.

    Нужно для 404 и 405: их производит роутер до операции, и «своей» операции у такого
    ответа нет — сверять его можно только с общим объявлением.
    """
    declarations = [
        _declared(document, path, method, status_code) for path, method, _ in _operations(document)
    ]
    assert declarations, "в схеме нет ни одной операции"
    assert all(item == declarations[0] for item in declarations), (
        f"объявление {status_code} различается по операциям"
    )
    return declarations[0]


async def test_validation_error_matches_its_declaration(
    document: dict[str, Any], client: AsyncClient
) -> None:
    """Ключевая сверка: FastAPI объявил бы 422, приложение отдаёт 400 validation_error."""
    path = f"{API}/auth/request-code"
    response = await client.post(path, json={"email": "не-почта"})

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"]["fields"], "details.fields пуст — SPEC.md 5.1 требует список полей"
    assert_response_matches_schema(document, "post", path, response)


async def test_not_found_matches_its_declaration(
    document: dict[str, Any], client: AsyncClient
) -> None:
    response = await client.get(f"{API}/no-such-route")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    declared = assert_declaration_is_global(document, 404)
    schema = declared["content"][JSON_MEDIA_TYPE]["schema"]
    assert_matches(document, schema, response.json(), "404")


async def test_method_not_allowed_matches_its_declaration(
    document: dict[str, Any], client: AsyncClient
) -> None:
    """405 в SPEC.md 5.1 нет, но фреймворк его порождает — значит фронт его увидит."""
    response = await client.post(f"{API}/version", json={})

    assert response.status_code == 405
    declared = assert_declaration_is_global(document, 405)
    schema = declared["content"][JSON_MEDIA_TYPE]["schema"]
    assert_matches(document, schema, response.json(), "405")


async def test_internal_error_matches_its_declaration(document: dict[str, Any]) -> None:
    """500 отдаёт только код и общее сообщение (S0-04) — схема обещает ровно это.

    Своего маршрута у 500 нет: производит его общий обработчик. Поэтому тело берётся
    у него, а объявление — у настоящей схемы приложения.
    """
    probe = FastAPI()
    register_error_handlers(probe)

    @probe.get("/boom")
    async def boom() -> None:
        raise ValueError("подробности только для лога")

    transport = ASGITransport(app=probe, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/boom")

    assert response.status_code == 500
    assert "подробности только для лога" not in response.text
    declared = assert_declaration_is_global(document, 500)
    schema = declared["content"][JSON_MEDIA_TYPE]["schema"]
    assert_matches(document, schema, response.json(), "500")
    # Пустой `details` — свойство обработчика, а не совпадение: закрытая схема ловит
    # первую же попытку вынести наружу что-то ещё.
    assert _details_schema(declared)["additionalProperties"] is False


async def test_generated_validation_error_is_absent(document: dict[str, Any]) -> None:
    """Модель, которой приложение не отдаёт, не должна остаться ни в ссылках, ни в components."""
    assert "HTTPValidationError" not in json.dumps(document)
    assert "ValidationError" not in document["components"]["schemas"]


async def test_every_reference_resolves(document: dict[str, Any]) -> None:
    """Снятый 422 не должен оставить висячую ссылку на удалённую модель."""

    def walk(node: Any, where: str) -> None:
        if isinstance(node, dict):
            if "$ref" in node:
                _resolve(document, node)
            for key, value in node.items():
                walk(value, f"{where}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{where}[{index}]")

    walk(document, "")


async def test_global_codes_declared_on_every_operation(document: dict[str, Any]) -> None:
    for path, method, _ in _operations(document):
        for status_code, codes in EXPECTED_GLOBAL_CODES.items():
            declared = _code_enum(_declared(document, path, method, status_code))
            assert codes <= declared, (
                f"{method.upper()} {path}: у {status_code} не объявлены {sorted(codes - declared)}"
            )


async def test_domain_codes_declared_on_their_endpoints(document: dict[str, Any]) -> None:
    for (path, method, status_code), codes in EXPECTED_DOMAIN_CODES.items():
        declared = _code_enum(_declared(document, path, method, status_code))
        assert codes <= declared, (
            f"{method.upper()} {path}: у {status_code} не объявлены {sorted(codes - declared)}"
        )
        # Доменные коды идут поверх общего набора, а не вместо него.
        assert EXPECTED_GLOBAL_CODES[status_code] <= declared


def _details_schema(declared: dict[str, Any]) -> dict[str, Any]:
    schema = declared["content"][JSON_MEDIA_TYPE]["schema"]
    details: dict[str, Any] = schema["properties"]["error"]["properties"]["details"]
    return details


async def test_validation_error_declares_its_fields(document: dict[str, Any]) -> None:
    """SPEC.md 5.1 связывает validation_error с details.fields — это часть контракта.

    Сверка тела такое не ловит: схема без `required` остаётся верной для любого ответа.
    """
    details = _details_schema(assert_declaration_is_global(document, 400))

    assert details["required"] == ["fields"]
    assert details["properties"]["fields"]["additionalProperties"] == {"type": "string"}


async def test_rate_limited_declares_retry_after(document: dict[str, Any]) -> None:
    """SPEC.md 5.1: «429 с retry_after». Обещает его только маршрут, который его отдаёт."""
    path = f"{API}/auth/request-code"
    details = _details_schema(_declared(document, path, "post", 429))

    assert details["required"] == ["retry_after"]
    assert details["properties"]["retry_after"]["type"] == "integer"
    # На остальных маршрутах 429 объявлен без него: другого производителя пока нет.
    assert "required" not in _details_schema(_declared(document, f"{API}/version", "get", 429))


async def test_error_code_dictionary_lists_declared_codes(document: dict[str, Any]) -> None:
    """`ErrorCode` — словарь для фронта: ровно то, что объявлено на операциях."""
    schemas = document["components"]["schemas"]
    expected = set().union(*EXPECTED_GLOBAL_CODES.values(), *EXPECTED_DOMAIN_CODES.values())

    assert set(schemas[ERROR_CODE_SCHEMA_NAME]["enum"]) == expected


async def test_error_model_is_declared_once(document: dict[str, Any]) -> None:
    """Общая модель ошибки — одна на API (ADR-0004), с кодом из словаря."""
    schemas = document["components"]["schemas"]
    error = schemas[ERROR_SCHEMA_NAME]

    assert error["required"] == ["error"]
    assert set(error["properties"]["error"]["required"]) == {"code", "message", "details"}
    assert error["properties"]["error"]["properties"]["code"] == {
        "$ref": f"#/components/schemas/{ERROR_CODE_SCHEMA_NAME}"
    }
