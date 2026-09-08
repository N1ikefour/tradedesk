"""Потолок на размер тела — `core/body_limit.py` (долг S1-01 перед S1-04).

Проверяется не «отдаёт 413», а то, ради чего мидлварь вообще написана: тело **не доходит
до разбора**. Сверка идёт по следу маршрута: он записывает длину дошедшего тела, и пустой
след означает, что управление до него не дошло. Один только ответ 413 этого не доказывает —
его отдала бы и проверка после парсинга.

Отдельно проверяется `Transfer-Encoding: chunked`: `Content-Length` там нет вовсе, и
мидлварь, полагающаяся только на заголовок, пропустила бы тело любого размера.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.body_limit import BodySizeLimitMiddleware
from app.core.errors import register_error_handlers

GUARDED = "/guarded"
FREE = "/free"
LIMIT = 512


@pytest.fixture
def seen() -> list[int]:
    return []


@pytest.fixture
def app(seen: list[int]) -> FastAPI:
    """Маршруты, которые записывают длину дошедшего до них тела."""
    application = FastAPI()
    register_error_handlers(application)

    @application.post(GUARDED)
    async def guarded(payload: dict[str, Any]) -> dict[str, int]:
        size = len(payload.get("value", ""))
        seen.append(size)
        return {"size": size}

    @application.post(FREE)
    async def free(payload: dict[str, Any]) -> dict[str, int]:
        size = len(payload.get("value", ""))
        seen.append(size)
        return {"size": size}

    application.add_middleware(BodySizeLimitMiddleware, max_bytes=LIMIT, paths=(GUARDED,))
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as opened:
        yield opened


def body(size: int) -> bytes:
    return b'{"value": "' + b"x" * size + b'"}'


async def stream(payload: bytes) -> AsyncIterator[bytes]:
    """Тело кусками: httpx отправит его без `Content-Length`, chunked."""
    for start in range(0, len(payload), 64):
        yield payload[start : start + 64]


JSON = {"content-type": "application/json"}


async def test_a_body_within_the_cap_reaches_the_route(
    client: AsyncClient, seen: list[int]
) -> None:
    response = await client.post(GUARDED, content=body(64), headers=JSON)

    assert response.status_code == 200
    assert seen == [64]


async def test_a_body_over_the_cap_is_refused_before_the_route(
    client: AsyncClient, seen: list[int]
) -> None:
    response = await client.post(GUARDED, content=body(LIMIT), headers=JSON)

    assert response.status_code == 413
    error = response.json()["error"]
    assert error["code"] == "payload_too_large"
    assert error["details"] == {"limit_bytes": LIMIT}
    assert seen == [], "тело дошло до маршрута — значит его успели разобрать"


async def test_a_chunked_body_over_the_cap_is_refused_too(
    client: AsyncClient, seen: list[int]
) -> None:
    """Без `Content-Length` заголовок не спасает: считать приходится сами байты."""
    response = await client.post(GUARDED, content=stream(body(LIMIT)), headers=JSON)

    assert response.status_code == 413
    assert seen == []


async def test_a_chunked_body_within_the_cap_arrives_whole(
    client: AsyncClient, seen: list[int]
) -> None:
    """Буферизованное тело обязано доехать до маршрута без потерь."""
    response = await client.post(GUARDED, content=stream(body(200)), headers=JSON)

    assert response.status_code == 200
    assert seen == [200]


async def test_a_lying_content_length_does_not_get_through(
    client: AsyncClient, seen: list[int]
) -> None:
    """Заголовок — дешёвый отсев, а не источник правды: решает счётчик байт."""
    response = await client.post(
        GUARDED,
        content=stream(body(LIMIT)),
        headers={**JSON, "content-length": "10"},
    )

    assert response.status_code == 413
    assert seen == []


async def test_other_paths_are_not_guarded(client: AsyncClient, seen: list[int]) -> None:
    """Мидлварь узкая по построению: свой потолок нужен своему потребителю."""
    response = await client.post(FREE, content=body(LIMIT * 4), headers=JSON)

    assert response.status_code == 200
    assert seen == [LIMIT * 4]


def test_the_ingest_route_is_the_one_that_is_guarded(local_env: pytest.MonkeyPatch) -> None:
    """Путь в настройке мидлвари обязан совпадать с настоящим маршрутом.

    Опечатка здесь молчит: приложение поднимается, ингест работает, а потолка нет.
    """
    from app.main import INGEST_DEALS_PATH, create_app

    paths = set(create_app().openapi()["paths"])

    assert INGEST_DEALS_PATH in paths


def test_the_cap_admits_the_largest_legal_batch() -> None:
    """Потолок не должен отсекать батч, который контракт разрешает.

    Оценка сверху по границам S1-01: 5000 сделок, у каждой символ до 64 символов и
    комментарий до 255. Если потолок опустят ниже неё, легальный синк начнёт получать 413
    и чиниться перезапуском не будет.
    """
    from app.domains.ingest.schemas import MAX_DEALS_PER_BATCH
    from app.main import INGEST_MAX_BODY_BYTES

    worst_case_deal_bytes = 700
    assert MAX_DEALS_PER_BATCH * worst_case_deal_bytes < INGEST_MAX_BODY_BYTES
