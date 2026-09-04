"""Контракт auth, не требующий живых зависимостей (S0-04).

Здесь только пути, которые обрываются до обращения к Postgres и Redis: валидация тела,
отсутствующая cookie, отклонённый Origin, наличие маршрута. Живой поток — в
tests/integration/test_auth.py.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.domains.auth.cookies import SESSION_COOKIE_NAME

API = "/api/v1"
ORIGIN = "http://test"


@pytest.fixture
async def client(
    unreachable_env: pytest.MonkeyPatch, make_app: Callable[[], FastAPI]
) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=make_app())
    async with AsyncClient(transport=transport, base_url=ORIGIN) as client:
        yield client


async def test_request_code_rejects_malformed_email(client: AsyncClient) -> None:
    response = await client.post(f"{API}/auth/request-code", json={"email": "not-an-email"})

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert "body.email" in body["error"]["details"]["fields"]


async def test_validation_error_does_not_echo_the_code(client: AsyncClient) -> None:
    """`input` ошибки pydantic несёт присланное значение — в ответ уходит только `msg`."""
    response = await client.post(
        f"{API}/auth/verify", json={"email": "user@example.com", "code": "1234567"}
    )

    assert response.status_code == 400
    assert "1234567" not in response.text


async def test_verify_requires_email_and_code(client: AsyncClient) -> None:
    response = await client.post(f"{API}/auth/verify", json={})

    assert response.status_code == 400
    assert set(response.json()["error"]["details"]["fields"]) == {"body.email", "body.code"}


async def test_me_without_cookie_is_401(client: AsyncClient) -> None:
    response = await client.get(f"{API}/auth/me")

    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "unauthorized"
    assert body["error"]["details"] == {}


async def test_me_with_garbage_cookie_is_401(client: AsyncClient) -> None:
    """Мусор в cookie равнозначен её отсутствию: до запроса в БД дело не доходит."""
    client.cookies.set(SESSION_COOKIE_NAME, "not-a-uuid")

    response = await client.get(f"{API}/auth/me")

    assert response.status_code == 401


async def test_logout_without_cookie_is_204(client: AsyncClient) -> None:
    response = await client.post(f"{API}/auth/logout")

    assert response.status_code == 204


async def test_mutating_request_from_foreign_origin_rejected(client: AsyncClient) -> None:
    response = await client.post(
        f"{API}/auth/request-code",
        json={"email": "user@example.com"},
        headers={"origin": "http://evil.example"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden_origin"


async def test_dev_outbox_is_absent_in_prod(
    unreachable_env: pytest.MonkeyPatch, make_app: Callable[[], FastAPI]
) -> None:
    """Письма содержат код входа: в проде маршрута нет ни в приложении, ни в схеме."""
    unreachable_env.setenv("APP_ENV", "prod")
    app = make_app()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=ORIGIN) as client:
        response = await client.get(f"{API}/dev/outbox")
        schema = await client.get(f"{API}/openapi.json")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert f"{API}/dev/outbox" not in schema.json()["paths"]


async def test_dev_outbox_is_published_in_local(client: AsyncClient) -> None:
    schema = await client.get(f"{API}/openapi.json")

    assert f"{API}/dev/outbox" in schema.json()["paths"]


async def test_unknown_email_provider_stops_startup(
    unreachable_env: pytest.MonkeyPatch, make_app: Callable[[], FastAPI]
) -> None:
    from app.core.config import ConfigError

    unreachable_env.setenv("EMAIL_PROVIDER", "resend")

    with pytest.raises(ConfigError, match="EMAIL_PROVIDER"):
        make_app()
