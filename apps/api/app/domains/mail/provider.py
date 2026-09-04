"""`EmailProvider` — интерфейс отправки письма (SPEC.md 4).

Отправка синхронная, за интерфейсом. SPEC.md 10 описывает `send_email` как задачу arq
с тремя ретраями; воркера в проекте ещё нет, а ConsoleEmailProvider пишет мгновенно.
Переезд на очередь меняет реализацию провайдера, а не место вызова (docs/tickets/S0-04.md).
"""

from __future__ import annotations

from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import ConfigError, Settings
from app.core.logging import get_logger
from app.domains.mail.models import DevOutboxEntry

log = get_logger(__name__)


class EmailProvider(Protocol):
    """Сигнатура из SPEC.md 4: `send(to, subject, text, html)`."""

    async def send(self, to: str, subject: str, text: str, html: str | None = None) -> None: ...


class ConsoleEmailProvider:
    """Письмо уходит в `dev_outbox` (страница /dev/outbox) и отмечается в логе.

    В лог идёт только факт отправки. Тело письма содержит одноразовый код, а код в логах
    не появляется никогда — это условие DoD S0-04 сильнее буквального «пишет в лог»
    из SPEC.md 4. Адрес получателя — персональные данные и в лог тоже не идёт;
    связать запись с письмом можно по `outbox_id`.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def send(self, to: str, subject: str, text: str, html: str | None = None) -> None:
        entry = DevOutboxEntry(to_email=to, subject=subject, body_text=text, body_html=html)
        self._session.add(entry)
        # flush, а не commit: письмо и otp_codes должны попасть в БД одной транзакцией.
        await self._session.flush()
        log.info("mail.sent", provider="console", subject=subject, outbox_id=str(entry.id))


def check_email_provider(settings: Settings) -> None:
    """Гейт старта: выбранный провайдер обязан существовать.

    `ResendEmailProvider` из SPEC.md 4 появится вместе с прод-развёрткой. Отказ на старте
    честнее, чем 500 на первой попытке входа.
    """
    if settings.email_provider != "console":
        raise ConfigError(
            f"EMAIL_PROVIDER={settings.email_provider}: провайдер ещё не реализован, "
            "в v1 доступен только console"
        )


def get_email_provider(settings: Settings, session: AsyncSession) -> EmailProvider:
    check_email_provider(settings)
    return ConsoleEmailProvider(session)
