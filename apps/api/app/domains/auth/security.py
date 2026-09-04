"""Секреты входа: одноразовый код, его хеш, идентификатор сессии."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from uuid import UUID, uuid4

CODE_LENGTH = 6
_CODE_UPPER_BOUND = 10**CODE_LENGTH


def generate_code() -> str:
    """Шесть цифр из криптографического источника. Ведущие нули значимы: код — строка."""
    return f"{secrets.randbelow(_CODE_UPPER_BOUND):0{CODE_LENGTH}d}"


def hash_code(code: str, pepper: str) -> str:
    """`sha256(code + OTP_PEPPER)` — форма из SPEC.md 3.1. Сам код не хранится нигде."""
    return hashlib.sha256(f"{code}{pepper}".encode()).hexdigest()


def code_matches(code: str, pepper: str, expected_hash: str) -> bool:
    # compare_digest: сравнение хешей за постоянное время, без утечки по таймингу.
    return hmac.compare_digest(hash_code(code, pepper), expected_hash)


def new_session_id() -> UUID:
    """uuid4, а не uuid7 из core/ids.py: значение уезжает в cookie, и старшие биты v7
    опубликовали бы время создания сессии. uuid4 в CPython берёт байты из os.urandom."""
    return uuid4()


def hash_rate_limit_subject(value: str, pepper: str) -> str:
    """Ключ Redis по адресу почты: сам адрес во вспомогательное хранилище не кладём."""
    return hashlib.sha256(f"{value}{pepper}".encode()).hexdigest()[:32]
