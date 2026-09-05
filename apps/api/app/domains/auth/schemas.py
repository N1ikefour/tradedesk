"""Тела запросов и ответов auth (SPEC.md 4)."""

from __future__ import annotations

import re
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import PydanticCustomError

from app.domains.auth.security import CODE_LENGTH

# 254 — предел длины адреса в RFC 5321.
EMAIL_MAX_LENGTH = 254
# Проверка намеренно грубая: полный грамматический разбор адреса даёт ложные отказы,
# а доставку всё равно подтверждает только письмо с кодом. Зависимость email-validator
# в SPEC.md 2.3 не разрешена.
# Управляющие символы C0/C1 вырезаются явно: `\s` покрывает только часть из них, а в
# заголовке письма любой такой символ — заготовка под инъекцию. Буквы вне ASCII остаются
# разрешёнными: IDN-адреса валидны.
_EMAIL_RE = re.compile(
    r"^[^@\s\x00-\x1f\x7f-\x9f]{1,64}"
    r"@[^@\s.\x00-\x1f\x7f-\x9f]+"
    r"(?:\.[^@\s.\x00-\x1f\x7f-\x9f]+)+$"
)
_CODE_RE = re.compile(rf"^\d{{{CODE_LENGTH}}}$")

EMAIL_ERROR = "Некорректный адрес электронной почты"
CODE_ERROR = f"Код состоит из {CODE_LENGTH} цифр"


def normalize_email(value: str) -> str:
    """Нижний регистр — форма хранения. Колонка citext, но ключ Redis чувствителен к регистру.

    PydanticCustomError, а не ValueError: последний уезжает в ответ с приставкой
    «Value error, », а SPEC.md 5.1 требует сообщение на русском и без служебного мусора.
    """
    email = value.strip().lower()
    if len(email) > EMAIL_MAX_LENGTH or not _EMAIL_RE.match(email):
        raise PydanticCustomError("email", EMAIL_ERROR)
    return email


class RequestCodeRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return normalize_email(value)


class RequestCodeResponse(BaseModel):
    """Ответ одинаков для существующего и несуществующего адреса (SPEC.md 4)."""

    status: Literal["accepted"] = "accepted"


class VerifyRequest(BaseModel):
    email: str
    # Длина ограничена до валидации регуляркой: строка на мегабайт не должна доходить до re.
    code: Annotated[str, Field(max_length=64)]

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        code = value.strip()
        if not _CODE_RE.match(code):
            raise PydanticCustomError("otp_code", CODE_ERROR)
        return code


class UserResponse(BaseModel):
    """Поля из SPEC.md 4, пункт 5.

    Общая модель для `/auth/me`, `/auth/verify` и `/users/me` (S0-08): один пользователь
    описывается в схеме одним компонентом. Правка полей здесь меняет ответ всех трёх.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    display_name: str | None
    timezone: str
    day_boundary_hour: int
