"""Alembic на async-движке. URL — только из окружения, никогда из alembic.ini."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import AsyncEngine

from alembic import context
from app.core.config import get_settings
from app.core.db import Base, create_engine

# Импорт ради побочного эффекта: без него модели не зарегистрированы в Base.metadata
# и autogenerate предложит удалить все таблицы. Новый домен с моделями — новая строка здесь.
from app.domains.accounts import models as accounts_models  # noqa: F401
from app.domains.auth import models as auth_models  # noqa: F401
from app.domains.ingest import models as ingest_models  # noqa: F401
from app.domains.journal import models as journal_models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    return get_settings().database_url.get_secret_value()


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run(connection: object) -> None:
    context.configure(
        connection=connection,  # type: ignore[arg-type]
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(_run_async(create_engine(get_settings())))


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
