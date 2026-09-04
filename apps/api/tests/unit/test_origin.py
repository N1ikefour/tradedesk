"""Проверка Origin на мутирующих запросах — CSRF из SPEC.md 4 (S0-04)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.errors import register_error_handlers
from app.core.origin import OriginCheckMiddleware, normalize_origin

APP_URL = "http://localhost:5173"
OWN_ORIGIN = "http://test"


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    register_error_handlers(app)
    app.add_middleware(OriginCheckMiddleware, app_url=APP_URL)

    @app.get("/probe")
    async def read() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/probe")
    async def write() -> dict[str, bool]:
        return {"ok": True}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=OWN_ORIGIN) as client:
        yield client


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("http://localhost:5173", "http://localhost:5173"),
        ("http://localhost:5173/", "http://localhost:5173"),
        ("https://App.Example.COM/path?q=1", "https://app.example.com"),
        ("  http://localhost:5173  ", "http://localhost:5173"),
        ("null", ""),
        ("", ""),
        ("localhost:5173", ""),
    ],
)
def test_normalize_origin(raw: str, expected: str) -> None:
    assert normalize_origin(raw) == expected


async def test_post_without_origin_passes(client: AsyncClient) -> None:
    """Коллектор и curl заголовок не ставят, а ambient-авторизации cookie у них нет."""
    response = await client.post("/probe")

    assert response.status_code == 200


@pytest.mark.parametrize("origin", [APP_URL, f"{APP_URL}/", OWN_ORIGIN])
async def test_post_from_allowed_origin_passes(client: AsyncClient, origin: str) -> None:
    response = await client.post("/probe", headers={"origin": origin})

    assert response.status_code == 200


@pytest.mark.parametrize(
    "origin",
    [
        "http://evil.example",
        "https://localhost:5173",
        "http://localhost:5174",
        "null",
        "http://localhost:5173.evil.example",
    ],
)
async def test_post_from_foreign_origin_rejected(client: AsyncClient, origin: str) -> None:
    response = await client.post("/probe", headers={"origin": origin})

    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "forbidden_origin"
    assert body["error"]["details"] == {}


async def test_get_from_foreign_origin_passes(client: AsyncClient) -> None:
    """SameSite=Lax не отдаёт cookie на кросс-сайтовые запросы, кроме навигационных GET."""
    response = await client.get("/probe", headers={"origin": "http://evil.example"})

    assert response.status_code == 200
