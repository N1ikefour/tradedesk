"""Контракт /accounts, не требующий живых зависимостей (S1-06).

Главное здесь — **пароль счёта не может появиться в ответе**. `CLAUDE.md` §5 и
SPEC.md 3.2 запрещают это безусловно, а дефект такого рода не виден в диффе: поле
добавляют в модель ответа одной строкой, и оно молча начинает уезжать клиенту.

Поэтому проверки две и обе смотрят не на код, а на схему, которую приложение объявляет:

* `test_account_response_declares_exactly_the_allowed_fields` — список полей заморожен.
  Любое новое поле ответа обязано пройти через правку этого теста, то есть через ревью.
* `test_no_accounts_response_leaks_a_secret_field` — рекурсивный обход всех успешных
  ответов домена по именам. Ловит утечку и там, где заморозить список нельзя: во
  вложенных моделях и в тех, что появятся позже.

Проверка значения (а не имени) — в `tests/integration/test_accounts.py`: там настоящий
пароль ищется в теле каждого ответа.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.openapi import JSON_MEDIA_TYPE
from app.domains.accounts.schemas import ACCOUNT_COLORS

API = "/api/v1"
ORIGIN = "http://test"
ACCOUNTS = f"{API}/accounts"
ACCOUNT = f"{ACCOUNTS}/{{account_id}}"

# Ровно то, что SPEC.md 5.2 обещает показать в карточке счёта. Список заморожен намеренно:
# правка этого множества — единственный способ добавить поле в ответ, и она видна в ревью.
ALLOWED_ACCOUNT_FIELDS = frozenset(
    {
        "id",
        "label",
        "is_demo",
        "color",
        "platform",
        "broker",
        "server",
        "login",
        "currency",
        "account_type",
        "server_utc_offset_minutes",
        "status",
        "status_message",
        "last_sync_at",
        "last_heartbeat_at",
        "collector_id",
        "sort_order",
        "created_at",
        "positions_count",
    }
)

# Подстроки, а не точные имена: `investor_password` и `password_hint` — такая же утечка,
# как `password`, и переименование поля не должно быть способом обойти проверку.
SECRET_NAME_MARKERS = (
    "password",
    "secret",
    "credential",
    "ciphertext",
    "wrapped",
    "key_version",
    "master_key",
    "token",
)


@pytest.fixture
def app(unreachable_env: pytest.MonkeyPatch, make_app: Callable[[], FastAPI]) -> FastAPI:
    """Зависимости смотрят в закрытый порт: до Postgres эти проверки не доходят.

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
    async with AsyncClient(transport=transport, base_url=ORIGIN) as client:
        yield client


def _resolve(document: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    reference = node.get("$ref")
    if reference is None:
        return node
    target: Any = document
    for part in reference.removeprefix("#/").split("/"):
        target = target[part]
    assert isinstance(target, dict)
    return target


def _component(document: dict[str, Any], name: str) -> dict[str, Any]:
    schema = document["components"]["schemas"][name]
    assert isinstance(schema, dict)
    return schema


def _accounts_operations(document: dict[str, Any]) -> Iterator[tuple[str, str, dict[str, Any]]]:
    for path, item in document["paths"].items():
        if not path.startswith(ACCOUNTS):
            continue
        for method, operation in item.items():
            if isinstance(operation, dict) and "responses" in operation:
                yield path, method, operation


def _property_names(document: dict[str, Any], node: Any, seen: set[str]) -> set[str]:
    """Все имена полей, достижимые из схемы. Циклы обрываются по имени компонента."""
    if isinstance(node, list):
        return set().union(*(_property_names(document, item, seen) for item in node), set())
    if not isinstance(node, dict):
        return set()
    reference = node.get("$ref")
    if reference is not None:
        if reference in seen:
            return set()
        seen = seen | {reference}
        return _property_names(document, _resolve(document, node), seen)
    found: set[str] = set()
    for key, value in node.items():
        if key == "properties" and isinstance(value, dict):
            found |= set(value)
        found |= _property_names(document, value, seen)
    return found


def _success_schemas(document: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    for path, method, operation in _accounts_operations(document):
        for status_code, response in operation["responses"].items():
            if not status_code.startswith("2"):
                continue
            content = response.get("content", {}).get(JSON_MEDIA_TYPE)
            if content is None:
                continue
            yield f"{method.upper()} {path} {status_code}", content["schema"]


# --- пароль не выходит наружу ------------------------------------------------


def test_account_response_declares_exactly_the_allowed_fields(document: dict[str, Any]) -> None:
    """Равенство, а не подмножество: и забытое поле, и лишнее — одинаково дефект."""
    model = _component(document, "AccountResponse")

    assert set(model["properties"]) == ALLOWED_ACCOUNT_FIELDS
    # Закрытая модель: конверт не пропустит наружу и то, что не объявлено.
    assert model["additionalProperties"] is False


def test_no_accounts_response_leaks_a_secret_field(document: dict[str, Any]) -> None:
    """Ни один успешный ответ домена не упоминает пароль — ни под каким именем."""
    leaks: list[str] = []
    for where, schema in _success_schemas(document):
        for name in _property_names(document, schema, set()):
            if any(marker in name.lower() for marker in SECRET_NAME_MARKERS):
                leaks.append(f"{where}: поле {name!r}")

    assert leaks == [], f"секрет в ответе: {leaks}"


def _variants(node: dict[str, Any]) -> list[dict[str, Any]]:
    """Сама схема плюс ветки `anyOf`: необязательное поле описано объединением с `null`."""
    return [node, *(item for item in node.get("anyOf", []) if isinstance(item, dict))]


def test_password_is_accepted_only_on_the_way_in(document: dict[str, Any]) -> None:
    """Обратная сторона: пароль обязан приниматься запросом, иначе счёт не завести.

    Без этой проверки предыдущая осталась бы зелёной и после удаления поля из запроса —
    то есть перестала бы что-либо доказывать.
    """
    for name in ("AccountCreateRequest", "AccountUpdateRequest"):
        model = _component(document, name)
        assert "password" in model["properties"], name
        # writeOnly: генераторы клиентов не положат его в тип ответа.
        assert any(
            variant.get("writeOnly") is True
            for variant in _variants(model["properties"]["password"])
        ), name


# --- форма контракта ---------------------------------------------------------


def test_color_palette_is_published_as_an_enum(document: dict[str, Any]) -> None:
    """Палитра из SPEC.md 3.2 приходит фронту из схемы, а не заводится второй копией."""
    declared = [
        variant.get("enum")
        for name in ("AccountCreateRequest", "AccountUpdateRequest")
        for variant in _variants(_component(document, name)["properties"]["color"])
    ]

    assert len(ACCOUNT_COLORS) == 8
    assert declared.count([*ACCOUNT_COLORS]) == 2


def test_patch_body_is_fully_optional_and_closed(document: dict[str, Any]) -> None:
    """PATCH частичный, лишнее поле — ошибка: опечатка иначе выглядит как «сохранено»."""
    model = _component(document, "AccountUpdateRequest")

    assert model.get("required", []) == []
    assert model["additionalProperties"] is False
    assert set(model["properties"]) == {
        "label",
        "is_demo",
        "color",
        "sort_order",
        "broker",
        "server",
        "login",
        "password",
    }


def test_only_broker_is_nullable_in_patch(document: dict[str, Any]) -> None:
    """Схема не должна обещать `null` там, где сервер его отвергает."""
    properties = _component(document, "AccountUpdateRequest")["properties"]

    assert {"type": "null"} in properties["broker"]["anyOf"]
    for name in ("label", "server", "color", "login", "sort_order", "is_demo"):
        assert "anyOf" not in properties[name], name


def test_times_are_declared_as_date_time(document: dict[str, Any]) -> None:
    """SPEC.md 5.1: время — ISO 8601. `PlainSerializer` без явной схемы дал бы `string`."""
    properties = _component(document, "AccountResponse")["properties"]

    assert properties["created_at"] == {
        "type": "string",
        "format": "date-time",
        "title": "Created At",
    }
    assert {"type": "string", "format": "date-time"} in properties["last_sync_at"]["anyOf"]


def test_sync_now_is_accepted_not_done(document: dict[str, Any]) -> None:
    """202 и ровно четыре поля расписки.

    Код ответа — часть смысла: `200` фронт вправе прочитать как «синхронизировано»,
    а забирает сделки коллектор, и произойти это может через минуту или не произойти
    вовсе. Список полей заморожен по той же причине, что и у карточки счёта.
    """
    operation = document["paths"][f"{ACCOUNT}/sync-now"]["post"]

    assert set(operation["responses"]) & {"200", "202"} == {"202"}
    model = _component(document, "SyncNowResponse")
    assert set(model["properties"]) == {
        "sync_requested_at",
        "last_sync_at",
        "last_heartbeat_at",
        "collector_online",
    }
    assert model["additionalProperties"] is False
    assert model["properties"]["sync_requested_at"] == {
        "type": "string",
        "format": "date-time",
        "title": "Sync Requested At",
    }


def test_delete_declares_no_body(document: dict[str, Any]) -> None:
    assert set(document["paths"][ACCOUNT]["delete"]["responses"]) >= {"204"}
    assert "content" not in document["paths"][ACCOUNT]["delete"]["responses"]["204"]


# --- доступ ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", ACCOUNTS),
        ("post", ACCOUNTS),
        ("patch", f"{ACCOUNTS}/00000000-0000-0000-0000-000000000000"),
        ("post", f"{ACCOUNTS}/00000000-0000-0000-0000-000000000000/pause"),
        ("post", f"{ACCOUNTS}/00000000-0000-0000-0000-000000000000/resume"),
        ("post", f"{ACCOUNTS}/00000000-0000-0000-0000-000000000000/archive"),
        ("post", f"{ACCOUNTS}/00000000-0000-0000-0000-000000000000/sync-now"),
        ("delete", f"{ACCOUNTS}/00000000-0000-0000-0000-000000000000"),
        ("get", f"{ACCOUNTS}/00000000-0000-0000-0000-000000000000/sync-runs"),
    ],
)
async def test_every_route_requires_a_session(client: AsyncClient, method: str, path: str) -> None:
    """401 раньше валидации тела: состав полей по ответу неаутентифицированный не узнает."""
    response = await client.request(method, path, json={})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", ACCOUNTS),
        ("patch", f"{ACCOUNTS}/00000000-0000-0000-0000-000000000000"),
        ("post", f"{ACCOUNTS}/00000000-0000-0000-0000-000000000000/sync-now"),
        ("delete", f"{ACCOUNTS}/00000000-0000-0000-0000-000000000000"),
    ],
)
async def test_mutations_are_guarded_by_origin(client: AsyncClient, method: str, path: str) -> None:
    """Проверка Origin из SPEC.md 4 распространяется на все мутирующие запросы."""
    response = await client.request(
        method, path, json={}, headers={"origin": "http://evil.example"}
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden_origin"
