"""Тело запроса на правку профиля (SPEC.md 5.7).

Ответ у профиля общий с `/auth/me` — `app.domains.auth.schemas.UserResponse`. Второй
модели здесь намеренно нет: два объявления одного и того же пользователя разъезжаются
молча, а фронт генерирует типы из схемы и получает два разных типа для одной сущности.
"""

from __future__ import annotations

import re
from functools import lru_cache
from zoneinfo import available_timezones

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.json_schema import SkipJsonSchema
from pydantic_core import PydanticCustomError

DISPLAY_NAME_MAX_LENGTH = 100
DAY_BOUNDARY_HOUR_MIN = 0
DAY_BOUNDARY_HOUR_MAX = 23

DISPLAY_NAME_TOO_LONG_ERROR = f"Имя не длиннее {DISPLAY_NAME_MAX_LENGTH} символов"
DISPLAY_NAME_CONTROL_ERROR = "Имя не должно содержать управляющие символы"
TIMEZONE_ERROR = "Неизвестная таймзона. Ожидается имя IANA, например Europe/Moscow"
TIMEZONE_REQUIRED_ERROR = "Таймзона не может быть пустой"
DAY_BOUNDARY_HOUR_ERROR = (
    f"Час начала торгового дня — целое число от {DAY_BOUNDARY_HOUR_MIN} до {DAY_BOUNDARY_HOUR_MAX}"
)
DAY_BOUNDARY_HOUR_REQUIRED_ERROR = "Час начала торгового дня не может быть пустым"

# Тот же класс символов, что вырезает `normalize_email`: имя попадает в письма и в UI,
# и управляющий символ там — заготовка под инъекцию, а не часть имени.
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")


@lru_cache(maxsize=1)
def known_timezones() -> frozenset[str]:
    """Имена IANA из tzdata окружения. Кэш: набор меняется только с обновлением образа.

    Сверка по множеству, а не `ZoneInfo(value)`: последняя на macOS с регистронезависимой
    файловой системой принимает `europe/moscow`, а в контейнере — нет. Валидация обязана
    решать одинаково везде, иначе локально зелёное значение падает в проде.
    """
    return frozenset(available_timezones())


class UserUpdateRequest(BaseModel):
    """Частичная правка профиля: отсутствующее поле не трогается.

    `display_name` — единственное обнуляемое: явный `null` очищает имя, чего отсутствие
    поля не делает. `timezone` и `day_boundary_hour` обнулить нельзя, `null` в них —
    ошибка валидации.
    """

    # extra="forbid": опечатка в имени поля иначе игнорируется, и пользователь видит
    # «сохранено» там, где не изменилось ничего.
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(
        default=None,
        description=(
            f"Отображаемое имя, не длиннее {DISPLAY_NAME_MAX_LENGTH} символов. "
            "null или пустая строка очищают имя"
        ),
    )
    # `SkipJsonSchema[None]` убирает `null` из схемы у необнуляемых полей: None здесь —
    # значение по умолчанию для «поле не прислано», а не разрешённый вход. Без него фронт
    # получил бы тип `string | null` для того, что сервер отвергает.
    timezone: str | SkipJsonSchema[None] = Field(
        default=None, description="Имя таймзоны IANA, например Europe/Moscow"
    )
    day_boundary_hour: int | SkipJsonSchema[None] = Field(
        default=None,
        description=(
            "Час начала торгового дня в таймзоне пользователя, "
            f"{DAY_BOUNDARY_HOUR_MIN}..{DAY_BOUNDARY_HOUR_MAX}"
        ),
    )

    @field_validator("display_name")
    @classmethod
    def _display_name(cls, value: str | None) -> str | None:
        """Пустое имя хранится как NULL: строка из пробелов — это отсутствие имени."""
        if value is None:
            return None
        name = value.strip()
        if not name:
            return None
        # Длина раньше поиска управляющих символов: регулярка по мегабайтной строке
        # не должна отрабатывать ради заведомо отклонённого значения.
        if len(name) > DISPLAY_NAME_MAX_LENGTH:
            raise PydanticCustomError("display_name", DISPLAY_NAME_TOO_LONG_ERROR)
        if _CONTROL_RE.search(name):
            raise PydanticCustomError("display_name", DISPLAY_NAME_CONTROL_ERROR)
        return name

    @field_validator("timezone")
    @classmethod
    def _timezone(cls, value: str | None) -> str:
        """Только имя IANA. Смещение `UTC+3` не проходит: оно врёт на переходе на летнее
        время, а у брокерских серверов свои зоны (SPEC.md 3.1, `server_utc_offset_minutes`).
        """
        if value is None:
            raise PydanticCustomError("timezone", TIMEZONE_REQUIRED_ERROR)
        name = value.strip()
        if name not in known_timezones():
            raise PydanticCustomError("timezone", TIMEZONE_ERROR)
        return name

    @field_validator("day_boundary_hour")
    @classmethod
    def _day_boundary_hour(cls, value: int | None) -> int:
        if value is None:
            raise PydanticCustomError("day_boundary_hour", DAY_BOUNDARY_HOUR_REQUIRED_ERROR)
        if not DAY_BOUNDARY_HOUR_MIN <= value <= DAY_BOUNDARY_HOUR_MAX:
            raise PydanticCustomError("day_boundary_hour", DAY_BOUNDARY_HOUR_ERROR)
        return value
