"""Контракт API: формат ошибок SPEC.md 5.1 и /health при недоступных зависимостях."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app import __version__
from app.core.errors import ApiError, register_error_handlers

API = "/api/v1"


async def _client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def client(
    local_env: pytest.MonkeyPatch, make_app: Callable[[], FastAPI]
) -> AsyncIterator[AsyncClient]:
    async with await _client(make_app()) as client:
        yield client


@pytest.fixture
async def error_probe_client() -> AsyncIterator[AsyncClient]:
    """Приложение с теми же обработчиками ошибок и маршрутами, которых нет в продукте.

    Проверять формат ошибок на боевых маршрутах нечем: в S0-02 существует только
    /health и /version, у которых нет ни параметров, ни доменных ошибок.
    """
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/probe")
    async def probe(limit: int) -> dict[str, int]:
        return {"limit": limit}

    @app.get("/domain-error")
    async def domain_error() -> None:
        raise ApiError(
            "account_not_found", "Счёт не найден", status_code=404, details={"account_id": "42"}
        )

    async with await _client(app) as client:
        yield client


async def test_version_returns_package_version(client: AsyncClient) -> None:
    response = await client.get(f"{API}/version")

    assert response.status_code == 200
    assert response.json() == {"version": __version__}


async def test_unknown_route_returns_spec_error_shape(client: AsyncClient) -> None:
    response = await client.get(f"{API}/no-such-route")

    assert response.status_code == 404
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details"}
    assert body["error"]["code"] == "not_found"
    assert body["error"]["details"] == {}


async def test_validation_error_is_400_with_fields(error_probe_client: AsyncClient) -> None:
    """FastAPI отдал бы 422; SPEC.md 5.1 требует 400 validation_error с details.fields."""
    response = await error_probe_client.get("/probe", params={"limit": "не-число"})

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert "query.limit" in error["details"]["fields"]


async def test_validation_error_does_not_echo_input(error_probe_client: AsyncClient) -> None:
    """Присланное значение не возвращается: во входе бывают секреты."""
    response = await error_probe_client.get("/probe", params={"limit": "hunter2"})

    assert "hunter2" not in response.text


async def test_domain_error_keeps_code_and_details(error_probe_client: AsyncClient) -> None:
    response = await error_probe_client.get("/domain-error")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "account_not_found",
            "message": "Счёт не найден",
            "details": {"account_id": "42"},
        }
    }


async def test_health_degraded_when_dependencies_unreachable(
    unreachable_env: pytest.MonkeyPatch, make_app: Callable[[], FastAPI]
) -> None:
    async with await _client(make_app()) as client:
        response = await client.get(f"{API}/health")

    # Недоступная зависимость не делает приложение нерабочим: 200, а не 500 и не 503.
    assert response.status_code == 200
    assert response.json() == {
        "status": "degraded",
        "db": "unavailable",
        "redis": "unavailable",
        "version": __version__,
    }
