"""Контракт маршрутов коллектора (S1-05), без живых зависимостей.

Главное здесь — **пароль счёта выходит наружу ровно одним маршрутом**. `CLAUDE.md` §5
и SPEC.md 5.6 разрешают это только `GET /internal/collector/assignments`, и проверка
смотрит не на код, а на схему, которую объявляет само приложение: любая вторая операция,
у которой в ответе появится пароль, красит этот файл.

Второе — дверь перед ним. Ответы на отсутствующий и на неверный токен обязаны быть
неразличимы, иначе подбирающий узнаёт, что форма `Bearer …` принята.

Третье — пароль не печатается **ни одним** объектом на этом пути. Их два: `Assignment`
собирает сервис, `AssignmentResponse` — роутер, и оба попадают в кадры стека. Защита на
одном из двух ничем не ловится, поэтому проверяются они разом.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response

from app.core.openapi import JSON_MEDIA_TYPE
from app.domains.accounts.models import TradingAccount
from app.domains.collector.schemas import AssignmentResponse
from app.domains.collector.service import Assignment

API = "/api/v1"
ASSIGNMENTS = f"{API}/internal/collector/assignments"
HEARTBEAT = f"{API}/ingest/heartbeat"
ORIGIN = "http://test"

TOKEN = "test-collector-token"

# Ровно то, что SPEC.md 5.6 обещает коллектору. Список заморожен: добавить поле в ответ,
# который несёт пароль, можно только правкой этого множества — то есть через ревью.
ALLOWED_ASSIGNMENT_FIELDS = frozenset(
    {
        "account_id",
        "server",
        "login",
        "password",
        "sync_requested_at",
        "last_sync_at",
        "status",
    }
)

SECRET_NAME_MARKERS = ("password", "secret", "credential", "ciphertext", "wrapped", "token")

# Значение, которого нет больше нигде: по нему обыскиваются repr обоих объектов.
REPR_PROBE_PASSWORD = "repr-probe-pw-4b7e0d"


@pytest.fixture
def app(unreachable_env: pytest.MonkeyPatch, make_app: Callable[[], FastAPI]) -> FastAPI:
    """Зависимости смотрят в закрытый порт: до Postgres эти проверки не доходят."""
    return make_app()


@pytest.fixture
def document(app: FastAPI) -> dict[str, Any]:
    return app.openapi()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=ORIGIN) as opened:
        yield opened


def _component(document: dict[str, Any], name: str) -> dict[str, Any]:
    schema = document["components"]["schemas"][name]
    assert isinstance(schema, dict)
    return schema


def _resolve(document: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    reference = node.get("$ref")
    if reference is None:
        return node
    target: Any = document
    for part in reference.removeprefix("#/").split("/"):
        target = target[part]
    assert isinstance(target, dict)
    return target


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
        return _property_names(document, _resolve(document, node), seen | {reference})
    found: set[str] = set()
    for key, value in node.items():
        if key == "properties" and isinstance(value, dict):
            found |= set(value)
        found |= _property_names(document, value, seen)
    return found


def _success_schemas(document: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    """Каждый успешный ответ каждой операции API — не только маршрутов коллектора."""
    for path, item in document["paths"].items():
        for method, operation in item.items():
            if not isinstance(operation, dict) or "responses" not in operation:
                continue
            for status_code, response in operation["responses"].items():
                if not status_code.startswith("2"):
                    continue
                content = response.get("content", {}).get(JSON_MEDIA_TYPE)
                if content is not None:
                    yield f"{method.upper()} {path}", content["schema"]


# --- пароль выходит ровно одним маршрутом ------------------------------------


def test_assignment_declares_exactly_the_allowed_fields(document: dict[str, Any]) -> None:
    """Равенство, а не подмножество: и забытое поле, и лишнее — одинаково дефект."""
    model = _component(document, "AssignmentResponse")

    assert set(model["properties"]) == ALLOWED_ASSIGNMENT_FIELDS
    assert model["additionalProperties"] is False


def test_password_appears_in_exactly_one_success_response(document: dict[str, Any]) -> None:
    """Обход всего API по именам: секрет под безобидным именем тоже считается утечкой."""
    leaking = sorted(
        where
        for where, schema in _success_schemas(document)
        for name in _property_names(document, schema, set())
        if any(marker in name.lower() for marker in SECRET_NAME_MARKERS)
    )

    assert leaking == [f"GET {ASSIGNMENTS}"], f"пароль в ответах: {leaking}"


def test_assignments_answer_with_an_items_envelope(document: dict[str, Any]) -> None:
    """SPEC.md 5.6: конверт, а не голый массив.

    Форма важна не эстетикой: курсорная пагинация из SPEC.md 5.1 добавляется полем рядом
    с `items`, а к массиву её пришлось бы приделывать ломающей правкой.
    """
    operation = document["paths"][ASSIGNMENTS]["get"]
    schema = _resolve(document, operation["responses"]["200"]["content"][JSON_MEDIA_TYPE]["schema"])

    assert set(schema["properties"]) == {"items"}
    assert schema["properties"]["items"]["type"] == "array"


def test_sync_requested_at_is_part_of_the_assignment(document: dict[str, Any]) -> None:
    """SPEC.md 5.6 требует его в ответе, иначе `POST /accounts/{id}/sync-now` — метка,
    которую никто не читает (требование пришло из ревью S1-06)."""
    model = _component(document, "AssignmentResponse")

    assert "sync_requested_at" in model["required"]


# --- пароль не печатается ни одним объектом пути ------------------------------


def _transient_account() -> TradingAccount:
    """Счёт в памяти: `repr` от базы не зависит, поднимать Postgres ради него незачем."""
    return TradingAccount(
        id=uuid4(),
        user_id=uuid4(),
        label="Демо",
        platform="mt5",
        is_demo=True,
        color="#000000",
        currency="USD",
        server="FTMO-Demo",
        login=7001234,
        status="pending",
    )


def _both_objects_on_the_path() -> list[tuple[str, object]]:
    """Оба объекта, через которые проходит расшифрованный пароль, — из одного счёта."""
    account = _transient_account()
    return [
        ("Assignment", Assignment(account=account, password=REPR_PROBE_PASSWORD)),
        ("AssignmentResponse", AssignmentResponse.issued(account, REPR_PROBE_PASSWORD)),
    ]


@pytest.mark.parametrize(
    "subject",
    [pytest.param(subject, id=name) for name, subject in _both_objects_on_the_path()],
)
def test_neither_object_prints_the_password(subject: object) -> None:
    """`repr` кадра стека — путь, по которому пароль уходит в лог и в Sentry.

    `scrub_unserializable` вырезает только **известные** секреты, а пароль счёта зашифрован
    и подстроки для скраба взять неоткуда (`CLAUDE.md` §5). Значит защита стоит на самих
    объектах — и обязана стоять на обоих: асимметрия ничем другим не ловится.
    """
    assert REPR_PROBE_PASSWORD not in repr(subject)
    assert REPR_PROBE_PASSWORD not in str(subject)


def test_password_still_travels_inside_both_objects() -> None:
    """Обратная половина: спрятать поле из `repr` — не то же, что убрать его из ответа.

    Без этой проверки «починка» вида `exclude=True` оставила бы тест выше зелёным и
    отправила бы коллектору задание без пароля.
    """
    by_name = dict(_both_objects_on_the_path())
    assignment = by_name["Assignment"]
    response = by_name["AssignmentResponse"]

    assert isinstance(assignment, Assignment)
    assert isinstance(response, AssignmentResponse)
    assert assignment.password == REPR_PROBE_PASSWORD
    assert response.model_dump()["password"] == REPR_PROBE_PASSWORD


# --- дверь перед ним ---------------------------------------------------------


def _bodies(*responses: Response) -> list[Any]:
    return [response.json() for response in responses]


async def test_missing_and_wrong_token_are_indistinguishable(client: AsyncClient) -> None:
    """Разные ответы подтвердили бы подбирающему, что форма `Bearer …` принята."""
    missing = await client.get(ASSIGNMENTS, params={"collector_id": "desk-01"})
    wrong = await client.get(
        ASSIGNMENTS,
        params={"collector_id": "desk-01"},
        headers={"authorization": "Bearer wrong-collector-token"},
    )
    malformed = await client.get(
        ASSIGNMENTS, params={"collector_id": "desk-01"}, headers={"authorization": TOKEN}
    )

    assert [response.status_code for response in (missing, wrong, malformed)] == [401, 401, 401]
    first, *rest = _bodies(missing, wrong, malformed)
    assert all(body == first for body in rest)
    assert first["error"]["code"] == "unauthorized"


async def test_heartbeat_is_closed_by_the_same_door(client: AsyncClient) -> None:
    response = await client.post(HEARTBEAT, json={"collector_id": "desk-01", "accounts": []})

    assert response.status_code == 401


async def test_unconfigured_token_closes_the_route(
    local_env: pytest.MonkeyPatch, make_app: Callable[[], FastAPI]
) -> None:
    """Пустой `COLLECTOR_TOKEN` совпал бы с пустым `Bearer` — и пароли ушли бы любому.

    В `local` секреты необязательны, поэтому «не задан» обязан значить «закрыто».
    """
    local_env.setenv("COLLECTOR_TOKEN", "")
    local_env.setenv("DATABASE_URL", "postgresql+asyncpg://td:td@127.0.0.1:1/td_test")
    transport = ASGITransport(app=make_app())
    async with AsyncClient(transport=transport, base_url=ORIGIN) as opened:
        responses = [
            await opened.get(ASSIGNMENTS, params={"collector_id": "desk-01"}),
            await opened.get(
                ASSIGNMENTS,
                params={"collector_id": "desk-01"},
                headers={"authorization": "Bearer "},
            ),
        ]

    assert [response.status_code for response in responses] == [401, 401]


async def test_configured_token_with_stray_whitespace_still_opens_the_door(
    unreachable_env: pytest.MonkeyPatch, make_app: Callable[[], FastAPI]
) -> None:
    """Присланный токен стрипается — ожидаемый обязан читаться так же.

    Иначе случайный пробел в `.env` даёт токен, который не совпадёт никогда, а вся
    диагностика сводится к `token_mismatch` в логе. Пустой heartbeat выбран потому, что
    до базы он не доходит: проверяется ровно дверь.
    """
    unreachable_env.setenv("COLLECTOR_TOKEN", f"  {TOKEN}\n")
    transport = ASGITransport(app=make_app())
    async with AsyncClient(transport=transport, base_url=ORIGIN) as opened:
        response = await opened.post(
            HEARTBEAT,
            json={"collector_id": "desk-01", "accounts": []},
            headers={"authorization": f"Bearer {TOKEN}"},
        )

    assert response.status_code == 200, response.text


async def test_token_is_never_echoed(client: AsyncClient) -> None:
    """Ни присланный токен, ни настоящий не возвращаются в теле отказа."""
    presented = "guessed-collector-token-12345"
    response = await client.get(
        ASSIGNMENTS,
        params={"collector_id": "desk-01"},
        headers={"authorization": f"Bearer {presented}"},
    )

    assert presented not in response.text
    assert TOKEN not in response.text


async def test_authorization_is_checked_before_the_query_is_validated(
    client: AsyncClient,
) -> None:
    """Без токена посторонний не должен даже узнать, какие параметры маршрут разбирает."""
    response = await client.get(ASSIGNMENTS)

    assert response.status_code == 401


def test_token_comparison_survives_a_non_ascii_token() -> None:
    """`compare_digest` на `str` требует ASCII и падает на кириллице в `COLLECTOR_TOKEN`.

    По HTTP такой токен не придёт (заголовки ASCII), но сравнение обязано отвечать
    «не совпало», а не рушить маршрут пятисоткой.
    """
    from app.domains.collector.dependencies import token_matches

    assert token_matches("токен-коллектора", "токен-коллектора") is True
    assert token_matches("guessed", "токен-коллектора") is False
