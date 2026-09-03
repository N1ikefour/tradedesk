"""/health против настоящих Postgres и Redis (testcontainers). Требует Docker."""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer

from app import __version__

pytestmark = pytest.mark.integration

API = "/api/v1"


@pytest.fixture(scope="module")
def postgres() -> Iterator[PostgresContainer]:
    # Имя БД с маркером _test: guard из core/db.py обязан пропускать её.
    with PostgresContainer("postgres:16-alpine", dbname="td_test") as container:
        yield container


@pytest.fixture(scope="module")
def redis_container() -> Iterator[RedisContainer]:
    with RedisContainer("redis:7-alpine") as container:
        yield container


@pytest.fixture
def live_env(
    local_env: pytest.MonkeyPatch,
    postgres: PostgresContainer,
    redis_container: RedisContainer,
) -> pytest.MonkeyPatch:
    url = postgres.get_connection_url().replace("postgresql+psycopg2://", "postgresql+asyncpg://")
    local_env.setenv("DATABASE_URL", url)
    local_env.setenv(
        "REDIS_URL",
        f"redis://{redis_container.get_container_host_ip()}:"
        f"{redis_container.get_exposed_port(6379)}/0",
    )
    return local_env


async def test_health_ok_with_live_dependencies(
    live_env: pytest.MonkeyPatch, make_app: Callable[[], FastAPI]
) -> None:
    app = make_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"{API}/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "db": "ok",
        "redis": "ok",
        "version": __version__,
    }


async def test_health_degraded_when_only_redis_down(
    live_env: pytest.MonkeyPatch, make_app: Callable[[], FastAPI]
) -> None:
    """БД жива, Redis нет: статусы независимы, приложение по-прежнему отвечает 200."""
    live_env.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    app = make_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"{API}/health")

    assert response.status_code == 200
    body = response.json()
    assert body["db"] == "ok"
    assert body["redis"] == "unavailable"
    assert body["status"] == "degraded"
