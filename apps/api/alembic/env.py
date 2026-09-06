"""Alembic на async-движке. URL — только из окружения, никогда из alembic.ini."""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncEngine

from alembic import context
from app.core.config import get_settings
from app.core.db import Base, create_engine
from app.core.logging import configure_logging

# Импорт ради побочного эффекта: без него модели не зарегистрированы в Base.metadata
# и autogenerate предложит удалить все таблицы. Новый домен с моделями — новая строка здесь.
from app.domains.accounts import models as accounts_models  # noqa: F401
from app.domains.analytics import models as analytics_models  # noqa: F401
from app.domains.auth import models as auth_models  # noqa: F401
from app.domains.ingest import models as ingest_models  # noqa: F401
from app.domains.journal import models as journal_models  # noqa: F401
from app.domains.mail import models as mail_models  # noqa: F401

config = context.config

# Логи миграций идут через общую настройку приложения, а не через `[logger_*]` секции
# alembic.ini: `fileConfig` переустанавливает root целиком (`level = WARNING`, handler
# в stderr, plain-формат), и в одном процессе с приложением — тесты, вызов alembic из
# кода — это глушит INFO всего приложения и ломает единственный формат логов.
#
# Секции alembic.ini при этом не теряются: `sqlalchemy` SQLAlchemy сама пинует в WARNING
# при импорте (log.py), а INFO самого alembic проходит по уровню root. Проверено, а не
# предположено: см. тест test_migrations_keep_application_logging_intact.
configure_logging(secret_values=get_settings().scrubbable_secret_values())

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
