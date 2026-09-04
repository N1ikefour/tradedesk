"""Логика входа по одноразовому коду — SPEC.md 4."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ApiError
from app.core.ids import uuid7
from app.core.rate_limit import RateLimit, RateLimiterUnavailableError, hit
from app.domains.auth import models
from app.domains.auth.cookies import SESSION_TTL_DAYS
from app.domains.auth.security import (
    code_matches,
    generate_code,
    hash_code,
    hash_rate_limit_subject,
    new_session_id,
)
from app.domains.mail.provider import EmailProvider

OTP_TTL = timedelta(minutes=10)
# После пятой неверной попытки код гасится — SPEC.md 4, пункт 2.
MAX_ATTEMPTS = 5

SESSION_TTL = timedelta(days=SESSION_TTL_DAYS)
# Скользящее продление: сессия трогается не чаще раза в сутки, иначе каждый запрос
# был бы записью в БД.
SESSION_TOUCH_INTERVAL = timedelta(days=1)
# User-Agent приходит от клиента: длину ограничиваем, чтобы строка не росла произвольно.
USER_AGENT_MAX_LENGTH = 512

REQUEST_CODE_EMAIL_LIMIT = RateLimit(limit=3, window_seconds=10 * 60)
REQUEST_CODE_IP_LIMIT = RateLimit(limit=10, window_seconds=60 * 60)
# Сколько просить подождать, когда счётчик не отвечает. Перебои Redis короткие, окно
# самого лимита (10 минут) здесь было бы напрасно пессимистичным.
RATE_LIMITER_DOWN_RETRY_AFTER = 60

EMAIL_SUBJECT = "TradeDesk: код для входа"

INVALID_CODE_CODE = "invalid_code"
INVALID_CODE_MESSAGE = "Неверный или просроченный код"
TOO_MANY_ATTEMPTS_CODE = "too_many_attempts"
TOO_MANY_ATTEMPTS_MESSAGE = "Слишком много неверных попыток. Запросите новый код"
RATE_LIMITED_CODE = "rate_limited"
RATE_LIMITED_MESSAGE = "Слишком много запросов кода. Попробуйте позже"
UNAUTHORIZED_CODE = "unauthorized"
UNAUTHORIZED_MESSAGE = "Требуется аутентификация"


def _now() -> datetime:
    return datetime.now(UTC)


def render_code_email(code: str) -> str:
    minutes = int(OTP_TTL.total_seconds() // 60)
    return (
        f"Код для входа в TradeDesk: {code}\n\n"
        f"Код действует {minutes} минут и подходит только для одного входа.\n"
        "Если вы не запрашивали вход, просто удалите это письмо."
    )


def unauthorized() -> ApiError:
    return ApiError(UNAUTHORIZED_CODE, UNAUTHORIZED_MESSAGE, status_code=401)


def _invalid_code() -> ApiError:
    return ApiError(INVALID_CODE_CODE, INVALID_CODE_MESSAGE, status_code=422)


def _rate_limited(retry_after: int) -> ApiError:
    return ApiError(
        RATE_LIMITED_CODE,
        RATE_LIMITED_MESSAGE,
        status_code=429,
        details={"retry_after": retry_after},
        headers={"Retry-After": str(retry_after)},
    )


async def _check_rate_limits(redis: Redis, settings: Settings, email: str, ip: str | None) -> None:
    """Порядок важен: IP-лимит проверяется первым, до инкремента счётчика по адресу почты.

    Обратный порядок означал бы, что запрос, отбитый общим лимитом по IP, дополнительно
    выжигает личную квоту пользователя — 3 запроса в 10 минут (X-06). За общим NAT или
    прокси пользователь, ничего не сделавший, терял бы и общий лимит, и свой.

    Недоступный Redis закрывает отправку, а не открывает её (fail-closed). Счётчик
    попыток в `otp_codes` ограничивает пять догадок **на код**, а не общий их бюджет:
    без лимита на выпуск кодов цикл «запросить новый код — сжечь пять попыток» перебирает
    шестизначное пространство, попутно рассылая письма на чужой адрес.

    Наружу это тот же `429`, что и обычное превышение: состояние инфраструктуры —
    не то, о чём стоит рассказывать неаутентифицированному клиенту. Настоящая причина
    видна в логе (`rate_limit.unavailable`).
    """
    pepper = settings.otp_pepper.get_secret_value()
    subject = hash_rate_limit_subject(email, pepper)
    try:
        retry_after = None
        if ip:
            retry_after = await hit(redis, f"rl:auth:request_code:ip:{ip}", REQUEST_CODE_IP_LIMIT)
        if retry_after is None:
            retry_after = await hit(
                redis, f"rl:auth:request_code:email:{subject}", REQUEST_CODE_EMAIL_LIMIT
            )
    except RateLimiterUnavailableError as exc:
        raise _rate_limited(RATE_LIMITER_DOWN_RETRY_AFTER) from exc
    if retry_after is not None:
        raise _rate_limited(retry_after)


async def request_code(
    *,
    session: AsyncSession,
    redis: Redis,
    settings: Settings,
    provider: EmailProvider,
    email: str,
    ip: str | None,
) -> None:
    """Создаёт код и отправляет письмо.

    Существование пользователя здесь не проверяется вовсе: SPEC.md 4 требует ответ,
    неотличимый для зарегистрированного и незнакомого адреса, а лишний запрос к users
    сделал бы ответы различимыми по времени. Пользователь заводится на verify.
    """
    await _check_rate_limits(redis, settings, email, ip)

    code = generate_code()
    now = _now()
    session.add(
        models.OtpCode(
            email=email,
            code_hash=hash_code(code, settings.otp_pepper.get_secret_value()),
            expires_at=now + OTP_TTL,
            attempts=0,
            created_at=now,
        )
    )
    # Письмо и код — одна транзакция: письмо без кода в базе вводило бы в заблуждение.
    await provider.send(to=email, subject=EMAIL_SUBJECT, text=render_code_email(code))
    await session.commit()


async def _active_code(session: AsyncSession, email: str) -> models.OtpCode | None:
    """Последний непогашенный код (SPEC.md 4, пункт 2).

    `with_for_update`: параллельные попытки не должны терять инкремент `attempts`,
    иначе перебор обходит лимит пятью одновременными запросами.
    """
    statement = (
        select(models.OtpCode)
        .where(models.OtpCode.email == email, models.OtpCode.consumed_at.is_(None))
        .order_by(models.OtpCode.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    return await session.scalar(statement)


async def _get_or_create_user(session: AsyncSession, email: str) -> models.User:
    """Первый удачный вход и есть регистрация (SPEC.md 4, пункт 2).

    ON CONFLICT DO NOTHING, а не select-then-insert: два одновременных входа с одного
    адреса иначе дают конфликт уникальности вместо второй сессии.
    """
    statement = (
        pg_insert(models.User)
        .values(id=uuid7(), email=email)
        .on_conflict_do_nothing(index_elements=["email"])
    )
    await session.execute(statement)
    user = await session.scalar(select(models.User).where(models.User.email == email))
    if user is None:  # pragma: no cover - недостижимо: строка либо вставлена, либо уже была
        raise RuntimeError("Пользователь не найден сразу после вставки")
    return user


async def verify(
    *,
    session: AsyncSession,
    settings: Settings,
    email: str,
    code: str,
    user_agent: str | None,
) -> tuple[models.User, models.Session]:
    """Проверяет код и открывает сессию. Ошибки — 422 с доменным кодом."""
    now = _now()
    otp = await _active_code(session, email)
    if otp is None or otp.expires_at <= now:
        # Просроченный код отбрасывается здесь, а не фоновой чисткой: воркера нет
        # (docs/tickets/S0-04.md). Строка остаётся в таблице до появления cleanup_otp.
        await session.rollback()
        raise _invalid_code()

    if not code_matches(code, settings.otp_pepper.get_secret_value(), otp.code_hash):
        otp.attempts += 1
        exhausted = otp.attempts >= MAX_ATTEMPTS
        if exhausted:
            otp.consumed_at = now
        await session.commit()
        if exhausted:
            raise ApiError(TOO_MANY_ATTEMPTS_CODE, TOO_MANY_ATTEMPTS_MESSAGE, status_code=422)
        raise _invalid_code()

    otp.consumed_at = now
    user = await _get_or_create_user(session, email)
    row = models.Session(
        id=new_session_id(),
        user_id=user.id,
        created_at=now,
        expires_at=now + SESSION_TTL,
        last_seen_at=now,
        user_agent=user_agent[:USER_AGENT_MAX_LENGTH] if user_agent else None,
    )
    session.add(row)
    await session.commit()
    return user, row


async def load_session(
    session: AsyncSession, session_id: UUID
) -> tuple[models.Session, models.User] | None:
    """Живая сессия и её владелец. Просроченная считается отсутствующей."""
    statement = (
        select(models.Session, models.User)
        .join(models.User, models.User.id == models.Session.user_id)
        .where(models.Session.id == session_id)
    )
    found = (await session.execute(statement)).first()
    if found is None:
        return None
    row, user = found
    if row.expires_at <= _now():
        return None
    return row, user


async def touch_session(session: AsyncSession, row: models.Session) -> bool:
    """Скользящее продление (SPEC.md 4, пункт 3). True, если сессия продлена."""
    now = _now()
    if row.last_seen_at is not None and now - row.last_seen_at <= SESSION_TOUCH_INTERVAL:
        return False
    row.last_seen_at = now
    row.expires_at = now + SESSION_TTL
    await session.commit()
    return True


async def logout(session: AsyncSession, session_id: UUID) -> None:
    await session.execute(delete(models.Session).where(models.Session.id == session_id))
    await session.commit()
