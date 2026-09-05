"""Тело запроса на правку профиля и список таймзон (SPEC.md 5.7).

Ответ у профиля общий с `/auth/me` — `app.domains.auth.schemas.UserResponse`. Второй
модели здесь намеренно нет: два объявления одного и того же пользователя разъезжаются
молча, а фронт генерирует типы из схемы и получает два разных типа для одной сущности.

`known_timezones()` — единственный источник имён зон: и то, что принимает `PATCH`, и то,
что отдаёт `GET /users/timezones`. Раздельные списки уже расходились: меню строилось из
`Intl.supportedValuesOf` браузера, а он для Индии, Украины и Вьетнама знает только
legacy-имена (`Asia/Calcutta`, `Europe/Kiev`), которых в tzdata образа нет — выбор такой
зоны заканчивался неустранимым 400.
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

# Управляющие символы C0/C1 — тот же класс, что отвергает `_EMAIL_RE` в auth: имя
# попадает в заголовки писем и в UI, а перевод строки там — заготовка под инъекцию.
# Разделители строк Unicode (U+2028/U+2029) и метки направления (U+200E/U+202E) сюда
# не входят: заголовок письма ими не разорвать, а имя с ними — валидное имя.
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")

# Оба имени лежат в /usr/share/zoneinfo и попадают в `available_timezones()`, но зонами
# пользователя не являются: `localtime` — ссылка на настройку конкретной машины и меняет
# смысл вместе с образом, `Factory` в самой tzdata означает «зона не настроена» (-00).
# Исключение стоит здесь, а не в маршруте: список один на валидацию и на выдачу, второе
# правило разъехалось бы с первым.
_NOT_USER_ZONES = frozenset({"Factory", "localtime"})


@lru_cache(maxsize=1)
def known_timezones() -> frozenset[str]:
    """Имена IANA из tzdata окружения. Кэш: набор меняется только с обновлением образа.

    Сверка по множеству, а не `ZoneInfo(value)`: последняя на macOS с регистронезависимой
    файловой системой принимает `europe/moscow`, а в контейнере — нет. Валидация обязана
    решать одинаково везде, иначе локально зелёное значение падает в проде.
    """
    return frozenset(available_timezones()) - _NOT_USER_ZONES


@lru_cache(maxsize=1)
def sorted_timezones() -> tuple[str, ...]:
    """Тот же набор в устойчивом порядке — тело `GET /users/timezones`.

    Сортировка на сервере, а не на клиенте: `available_timezones()` отдаёт множество, и
    порядок обхода меняется от запуска к запуску. Без неё ответ отличался бы побайтно при
    том же содержимом, и ETag перестал бы что-либо значить.

    Группировки по смещению здесь нет намеренно: смещение зависит от даты (переходы на
    летнее время), поэтому считать его — дело клиента, который знает, какой день показывает.
    """
    return tuple(sorted(known_timezones()))


class TimezonesResponse(BaseModel):
    """Список имён зон, которые принимает `PATCH /users/me`."""

    items: list[str] = Field(description="Имена таймзон IANA, отсортированы лексикографически")


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

    @field_validator("day_boundary_hour", mode="before")
    @classmethod
    def _day_boundary_hour_is_not_bool(cls, value: object) -> object:
        """`true` — не «час 1». В Python bool наследует int, и мягкий режим pydantic
        пропускает его в поле как 1: клиент прислал бы явную ошибку, а получил «сохранено».
        Строку `"7"` при этом принимаем — она приходит из поля формы.
        """
        if isinstance(value, bool):
            raise PydanticCustomError("day_boundary_hour", DAY_BOUNDARY_HOUR_ERROR)
        return value

    @field_validator("day_boundary_hour")
    @classmethod
    def _day_boundary_hour(cls, value: int | None) -> int:
        if value is None:
            raise PydanticCustomError("day_boundary_hour", DAY_BOUNDARY_HOUR_REQUIRED_ERROR)
        if not DAY_BOUNDARY_HOUR_MIN <= value <= DAY_BOUNDARY_HOUR_MAX:
            raise PydanticCustomError("day_boundary_hour", DAY_BOUNDARY_HOUR_ERROR)
        return value
