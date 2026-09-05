"""Контракт /users/me, не требующий живых зависимостей (S0-08).

Здесь пути, которые обрываются до Postgres: отсутствующая cookie, чужой Origin, форма
ответа в схеме, разбор условного GET. Живой профиль и правка — в
tests/integration/test_users.py.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.openapi import JSON_MEDIA_TYPE
from app.domains.auth.cookies import SESSION_COOKIE_NAME
from app.domains.users import router as users_router

API = "/api/v1"
ORIGIN = "http://test"
USERS_ME = f"{API}/users/me"
AUTH_ME = f"{API}/auth/me"
TIMEZONES = f"{API}/users/timezones"


@pytest.fixture
def app(unreachable_env: pytest.MonkeyPatch, make_app: Callable[[], FastAPI]) -> FastAPI:
    """Импорт `app.main` — внутри фабрики `make_app` (X-09): на уровне модуля он собрал бы
    приложение с настройками из .env раньше, чем фикстуры их подменят.
    """
    return make_app()


@pytest.fixture
def document(app: FastAPI) -> dict[str, Any]:
    return app.openapi()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=ORIGIN) as client:
        yield client


def success_schema(document: dict[str, Any], path: str, method: str) -> dict[str, Any]:
    response = document["paths"][path][method]["responses"]["200"]
    schema = response["content"][JSON_MEDIA_TYPE]["schema"]
    assert isinstance(schema, dict)
    return schema


# --- общая модель ответа -----------------------------------------------------


def test_users_me_and_auth_me_share_the_response_model(document: dict[str, Any]) -> None:
    """Сравнение, а не утверждение: разъехавшиеся модели дали бы фронту два типа на одну
    сущность, и заметить это можно было бы только в UI.
    """
    users_get = success_schema(document, USERS_ME, "get")
    users_patch = success_schema(document, USERS_ME, "patch")
    auth_get = success_schema(document, AUTH_ME, "get")
    auth_verify = success_schema(document, f"{API}/auth/verify", "post")

    assert users_get == auth_get == users_patch == auth_verify
    # Именно $ref, а не совпавшая инлайновая копия: копии расходятся при первой же правке.
    assert "$ref" in users_get


def test_response_model_carries_the_settings_fields(document: dict[str, Any]) -> None:
    reference = success_schema(document, USERS_ME, "get")["$ref"].rsplit("/", 1)[-1]
    model = document["components"]["schemas"][reference]

    assert set(model["properties"]) == {
        "id",
        "email",
        "display_name",
        "timezone",
        "day_boundary_hour",
    }


def test_patch_body_is_fully_optional_and_closed(document: dict[str, Any]) -> None:
    """Все поля необязательны — PATCH частичный; лишние запрещены — опечатка видна."""
    body = document["paths"][USERS_ME]["patch"]["requestBody"]
    reference = body["content"][JSON_MEDIA_TYPE]["schema"]["$ref"].rsplit("/", 1)[-1]
    model = document["components"]["schemas"][reference]

    assert model.get("required", []) == []
    assert model["additionalProperties"] is False
    assert set(model["properties"]) == {"display_name", "timezone", "day_boundary_hour"}


def test_only_display_name_is_nullable_in_the_schema(document: dict[str, Any]) -> None:
    """Схема не должна обещать фронту `null` там, где сервер его отвергает."""
    reference = (
        document["paths"][USERS_ME]["patch"]["requestBody"]["content"][JSON_MEDIA_TYPE]["schema"][
            "$ref"
        ]
    ).rsplit("/", 1)[-1]
    properties = document["components"]["schemas"][reference]["properties"]

    assert {"type": "null"} in properties["display_name"]["anyOf"]
    assert properties["timezone"]["type"] == "string"
    assert properties["day_boundary_hour"]["type"] == "integer"


# --- список таймзон ----------------------------------------------------------


def test_timezones_response_is_a_list_of_strings(document: dict[str, Any]) -> None:
    reference = success_schema(document, TIMEZONES, "get")["$ref"].rsplit("/", 1)[-1]
    model = document["components"]["schemas"][reference]

    assert model["properties"]["items"]["type"] == "array"
    assert model["properties"]["items"]["items"]["type"] == "string"


def test_timezones_declares_not_modified(document: dict[str, Any]) -> None:
    """Фронт обязан знать про 304: без объявления сгенерированный клиент считает его
    неожиданным ответом, а маршрут отдаёт его на каждой ревалидации.
    """
    assert "304" in document["paths"][TIMEZONES]["get"]["responses"]


# --- ETag списка таймзон -----------------------------------------------------


@pytest.fixture
def etag_of(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[[tuple[str, ...]], str]]:
    """Считает тег для подставленного набора имён.

    `timezones_etag` читает список без аргументов и кэширован на процесс, поэтому кэш
    сбрасывается перед каждым подсчётом и ещё раз после теста: подставленный набор,
    оставшийся в кэше, отдавал бы чужой тег соседним тестам.
    """

    def compute(zones: tuple[str, ...]) -> str:
        monkeypatch.setattr(users_router, "sorted_timezones", lambda: zones)
        users_router.timezones_etag.cache_clear()
        return users_router.timezones_etag()

    yield compute
    users_router.timezones_etag.cache_clear()


def test_timezones_etag_follows_the_list_contents(
    etag_of: Callable[[tuple[str, ...]], str],
) -> None:
    """То, чего не проверяет round-trip: разное содержимое обязано давать разные теги.

    «Тот же тег → 304, чужой тег → 200» остаётся верным и для константы вместо хеша, а
    константа означает вечный 304 — клиент навсегда остался бы со списком той версии,
    которую скачал первым.
    """
    base = etag_of(("Europe/Moscow", "UTC"))

    assert etag_of(("Europe/Moscow", "UTC")) == base
    assert etag_of(("Europe/Moscow", "UTC", "Asia/Tokyo")) != base
    assert etag_of(("Europe/Moscow", "Asia/Tokyo")) != base
    assert etag_of(()) != base


def test_timezones_etag_is_a_strong_quoted_tag(
    etag_of: Callable[[tuple[str, ...]], str],
) -> None:
    """RFC 9110 §8.8.3: значение — строка в кавычках. Без них заголовок невалиден."""
    etag = etag_of(("Europe/Moscow", "UTC"))

    assert etag.startswith('"')
    assert etag.endswith('"')


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ('"tag"', True),
        # Слабая форма: тождественности байтов она не обещает, но для выбора «отдавать
        # ли тело» этого достаточно.
        ('W/"tag"', True),
        ('"other", "tag"', True),
        ('W/"other" , "tag"', True),
        # RFC 9110 §13.1.2: `*` совпадает с любым существующим представлением.
        ("*", True),
        (" * ", True),
        ('"other"', False),
        # Кавычки делают из подстановки обычный тег, который с нашим не совпадает.
        ('"*"', False),
        ('"ta"', False),
        ("", False),
        (None, False),
    ],
)
def test_if_none_match_is_parsed_per_rfc(header: str | None, expected: bool) -> None:
    assert users_router._matches_etag(header, '"tag"') is expected


# --- доступ ------------------------------------------------------------------


async def test_get_without_cookie_is_401(client: AsyncClient) -> None:
    response = await client.get(USERS_ME)

    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "unauthorized"
    assert body["error"]["details"] == {}


async def test_patch_without_cookie_is_401(client: AsyncClient) -> None:
    """Валидация pydantic не доходит до неаутентифицированного: состав и правила полей
    он по ответу не восстановит.
    """
    response = await client.patch(USERS_ME, json={"timezone": "Europe/Moscow"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_broken_json_without_cookie_is_400_and_names_no_fields(client: AsyncClient) -> None:
    """Граница гарантии из теста выше: сырое тело FastAPI читает раньше зависимостей,
    поэтому синтаксически битый JSON даёт 400 и без сессии. Наружу при этом уходит только
    «тело не разобрано» — ни одного имени поля.
    """
    response = await client.patch(
        USERS_ME, content=b"{not json", headers={"content-type": "application/json"}
    )

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert not {"timezone", "display_name", "day_boundary_hour"} & set(
        body["error"]["details"]["fields"]
    )


async def test_timezones_without_cookie_is_401(client: AsyncClient) -> None:
    """Список — часть ресурса профиля и живёт под сессией, как весь `/users`."""
    response = await client.get(TIMEZONES)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_patch_with_garbage_cookie_is_401(client: AsyncClient) -> None:
    client.cookies.set(SESSION_COOKIE_NAME, "not-a-uuid")

    response = await client.patch(USERS_ME, json={"timezone": "Europe/Moscow"})

    assert response.status_code == 401


async def test_patch_from_foreign_origin_rejected(client: AsyncClient) -> None:
    """PATCH — мутирующий запрос, проверка Origin из SPEC.md 4 на него распространяется."""
    response = await client.patch(
        USERS_ME,
        json={"timezone": "Europe/Moscow"},
        headers={"origin": "http://evil.example"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden_origin"


async def test_get_is_not_guarded_by_origin(client: AsyncClient) -> None:
    """Чтение остаётся чтением: 401 из-за отсутствующей сессии, а не 403 из-за Origin."""
    response = await client.get(USERS_ME, headers={"origin": "http://evil.example"})

    assert response.status_code == 401
