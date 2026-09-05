"""Тела запросов и ответов счетов — SPEC.md 5.2.

⚠️ Пароль счёта не входит ни в одну модель ответа и не может войти. `CLAUDE.md` §5 и
SPEC.md 3.2: он читается только `GET /internal/collector/assignments` (S1-05). Поэтому
`AccountResponse` собирается полем за полем в `from_account`, а не `model_validate`
поверх ORM-объекта: список полей ответа — явный текст, который видно в диффе. Инвариант
закрыт тестами `tests/unit/test_accounts_contract.py` и сканом настоящих тел ответов
в `tests/integration/test_accounts.py`.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Literal, get_args
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from pydantic.json_schema import SkipJsonSchema
from pydantic_core import PydanticCustomError

from app.core.schemas import UtcDatetime
from app.domains.accounts import models
from app.domains.ingest import models as ingest_models

LABEL_MAX_LENGTH = 60
BROKER_MAX_LENGTH = 100
SERVER_MAX_LENGTH = 128
PASSWORD_MAX_LENGTH = 256
# MT5 отдаёт номер счёта целым; колонка — bigint (SPEC.md 3.2).
LOGIN_MIN = 1
LOGIN_MAX = 2**63 - 1
SORT_ORDER_MIN = -32768
SORT_ORDER_MAX = 32767

LABEL_REQUIRED_ERROR = "Название счёта не может быть пустым"
LABEL_TOO_LONG_ERROR = f"Название не длиннее {LABEL_MAX_LENGTH} символов"
CONTROL_CHARS_ERROR = "Значение не должно содержать управляющие символы"
BROKER_TOO_LONG_ERROR = f"Название брокера не длиннее {BROKER_MAX_LENGTH} символов"
SERVER_REQUIRED_ERROR = "Сервер не может быть пустым"
SERVER_TOO_LONG_ERROR = f"Имя сервера не длиннее {SERVER_MAX_LENGTH} символов"
LOGIN_ERROR = "Логин — целое положительное число"
PASSWORD_REQUIRED_ERROR = "Пароль не может быть пустым"
PASSWORD_TOO_LONG_ERROR = f"Пароль не длиннее {PASSWORD_MAX_LENGTH} символов"
PASSWORD_CONTROL_ERROR = "Пароль не должен содержать переводы строк и управляющие символы"
SORT_ORDER_ERROR = f"Порядок сортировки — целое от {SORT_ORDER_MIN} до {SORT_ORDER_MAX}"
NULL_NOT_ALLOWED_ERROR = "Значение не может быть null"

MT5_REQUIRED_ERROR = "Для счёта MT5 обязательны server, login и password"
MT5_ONLY_ERROR = "Поля server, login и password есть только у счетов MT5"

# Тот же класс символов, что отвергают схемы auth и users: строка уезжает в UI и в логи.
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")

AccountPlatform = Literal["mt5", "csv", "manual"]
AccountType = Literal["hedging", "netting"]
AccountStatus = Literal["pending", "connected", "needs_attention", "paused", "archived"]

# Палитра из SPEC.md 3.2 («hex, из палитры 8 цветов»). Объявлена `Literal`, а не свободной
# строкой, ровно затем, чтобы попасть в OpenAPI перечислением: тогда у фронта (S1-11) она
# берётся из `make types`, а не заводится второй копией, которая разойдётся с этой.
AccountColor = Literal[
    "#2563eb",
    "#16a34a",
    "#dc2626",
    "#d97706",
    "#7c3aed",
    "#0891b2",
    "#db2777",
    "#65a30d",
]
ACCOUNT_COLORS: tuple[str, ...] = get_args(AccountColor)

# SecretStr, а не str: в `repr` модели запроса пароль иначе печатается целиком, а `repr`
# уезжает и в traceback, и в лог через `scrub_unserializable` (S0-04).
Password = Annotated[SecretStr, Field(description="Пароль инвестора. В ответах не возвращается")]


def _reject_control_chars(value: str, code: str, error: str = CONTROL_CHARS_ERROR) -> str:
    if _CONTROL_RE.search(value):
        raise PydanticCustomError(code, error)
    return value


def validate_label(value: str) -> str:
    label = value.strip()
    if not label:
        raise PydanticCustomError("label", LABEL_REQUIRED_ERROR)
    # Длина раньше регулярки: строка на мегабайт не должна доходить до поиска.
    if len(label) > LABEL_MAX_LENGTH:
        raise PydanticCustomError("label", LABEL_TOO_LONG_ERROR)
    return _reject_control_chars(label, "label")


def validate_broker(value: str | None) -> str | None:
    """`null` и пустая строка одинаково означают «брокер не указан»."""
    if value is None:
        return None
    broker = value.strip()
    if not broker:
        return None
    if len(broker) > BROKER_MAX_LENGTH:
        raise PydanticCustomError("broker", BROKER_TOO_LONG_ERROR)
    return _reject_control_chars(broker, "broker")


def validate_server(value: str) -> str:
    server = value.strip()
    if not server:
        raise PydanticCustomError("server", SERVER_REQUIRED_ERROR)
    if len(server) > SERVER_MAX_LENGTH:
        raise PydanticCustomError("server", SERVER_TOO_LONG_ERROR)
    return _reject_control_chars(server, "server")


def validate_login(value: int) -> int:
    if not LOGIN_MIN <= value <= LOGIN_MAX:
        raise PydanticCustomError("login", LOGIN_ERROR)
    return value


def validate_sort_order(value: int) -> int:
    if not SORT_ORDER_MIN <= value <= SORT_ORDER_MAX:
        raise PydanticCustomError("sort_order", SORT_ORDER_ERROR)
    return value


def validate_password(value: SecretStr) -> SecretStr:
    """Пробелы не срезаются: у пароля они значащие. Управляющие символы — отвергаются.

    Перевод строки в пароле — это вставка из письма или из файла, а не пароль: MT5 такой
    не примет, и сказать об этом здесь дешевле, чем оставить счёт в `needs_attention`
    с непонятной ошибкой терминала.
    """
    secret = value.get_secret_value()
    if not secret:
        raise PydanticCustomError("password", PASSWORD_REQUIRED_ERROR)
    if len(secret) > PASSWORD_MAX_LENGTH:
        raise PydanticCustomError("password", PASSWORD_TOO_LONG_ERROR)
    if _CONTROL_RE.search(secret):
        raise PydanticCustomError("password", PASSWORD_CONTROL_ERROR)
    return value


def _reject_bool(value: object, code: str, error: str) -> object:
    """`true` — не «единица». В Python bool наследует int, и мягкий режим pydantic
    пропустил бы его в числовое поле молча.
    """
    if isinstance(value, bool):
        raise PydanticCustomError(code, error)
    return value


class AccountCreateRequest(BaseModel):
    """Тело `POST /accounts` (SPEC.md 5.2)."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(description="Название счёта, например «Демо FTMO»")
    platform: AccountPlatform = Field(description="Источник сделок")
    is_demo: bool = Field(default=False, description="Демо-счёт")
    color: AccountColor | None = Field(
        default=None,
        description="Цвет из палитры. Если не задан — назначается первый свободный",
    )
    broker: str | None = Field(default=None, description="Брокер, свободный текст")
    server: str | None = Field(default=None, description="Сервер MT5, например FTMO-Demo")
    login: int | None = Field(default=None, description="Номер счёта MT5")
    password: Password | None = Field(default=None)
    sort_order: int = Field(default=0, description="Порядок в переключателе счетов")

    @field_validator("label")
    @classmethod
    def _label(cls, value: str) -> str:
        return validate_label(value)

    @field_validator("broker")
    @classmethod
    def _broker(cls, value: str | None) -> str | None:
        return validate_broker(value)

    @field_validator("server")
    @classmethod
    def _server(cls, value: str | None) -> str | None:
        return None if value is None else validate_server(value)

    @field_validator("login", "sort_order", mode="before")
    @classmethod
    def _numbers_are_not_bool(cls, value: object) -> object:
        return _reject_bool(value, "not_a_number", LOGIN_ERROR)

    @field_validator("login")
    @classmethod
    def _login(cls, value: int | None) -> int | None:
        return None if value is None else validate_login(value)

    @field_validator("sort_order")
    @classmethod
    def _sort_order(cls, value: int) -> int:
        return validate_sort_order(value)

    @field_validator("password")
    @classmethod
    def _password(cls, value: SecretStr | None) -> SecretStr | None:
        return None if value is None else validate_password(value)

    @model_validator(mode="after")
    def _platform_fields(self) -> AccountCreateRequest:
        """Связка полей зависит от платформы — проверить её может только модель целиком."""
        mt5_fields: tuple[object, ...] = (self.server, self.login, self.password)
        if self.platform == "mt5":
            if any(value is None for value in mt5_fields):
                raise PydanticCustomError("platform_fields", MT5_REQUIRED_ERROR)
        elif any(value is not None for value in mt5_fields):
            raise PydanticCustomError("platform_fields", MT5_ONLY_ERROR)
        return self


class AccountUpdateRequest(BaseModel):
    """Тело `PATCH /accounts/{id}` — частичное: отсутствующее поле не трогается.

    `broker` — единственное обнуляемое: явный `null` очищает брокера. Остальные поля
    обнулить нечем, `null` в них — ошибка валидации, а не «сбрось значение».

    ⚠️ Присутствие `password` или **изменение** `server`/`login` сбрасывает статус
    (см. `service.update_account`). Форма редактирования отправляет карточку целиком,
    поэтому решает не присутствие поля, а разница значений: иначе переименование счёта
    останавливало бы работающий синк.
    """

    model_config = ConfigDict(extra="forbid")

    # `SkipJsonSchema[None]` убирает `null` из схемы: None здесь — значение по умолчанию
    # для «поле не прислано», а не разрешённый вход (тот же приём, что в users/schemas.py).
    label: str | SkipJsonSchema[None] = Field(default=None)
    is_demo: bool | SkipJsonSchema[None] = Field(default=None)
    color: AccountColor | SkipJsonSchema[None] = Field(default=None)
    sort_order: int | SkipJsonSchema[None] = Field(default=None)
    broker: str | None = Field(default=None, description="null очищает брокера")
    server: str | SkipJsonSchema[None] = Field(default=None)
    login: int | SkipJsonSchema[None] = Field(default=None)
    password: Password | SkipJsonSchema[None] = Field(default=None)

    @field_validator("label", "is_demo", "color", "server", "password", mode="before")
    @classmethod
    def _null_is_not_an_operation(cls, value: object) -> object:
        if value is None:
            raise PydanticCustomError("null_not_allowed", NULL_NOT_ALLOWED_ERROR)
        return value

    @field_validator("label")
    @classmethod
    def _label(cls, value: str | None) -> str | None:
        return None if value is None else validate_label(value)

    @field_validator("broker")
    @classmethod
    def _broker(cls, value: str | None) -> str | None:
        return validate_broker(value)

    @field_validator("server")
    @classmethod
    def _server(cls, value: str | None) -> str | None:
        return None if value is None else validate_server(value)

    @field_validator("login", "sort_order", mode="before")
    @classmethod
    def _numbers_are_not_bool(cls, value: object) -> object:
        return _reject_bool(value, "not_a_number", LOGIN_ERROR)

    @field_validator("login")
    @classmethod
    def _login(cls, value: int | None) -> int | None:
        if value is None:
            raise PydanticCustomError("login", LOGIN_ERROR)
        return validate_login(value)

    @field_validator("sort_order")
    @classmethod
    def _sort_order(cls, value: int | None) -> int | None:
        if value is None:
            raise PydanticCustomError("sort_order", SORT_ORDER_ERROR)
        return validate_sort_order(value)

    @field_validator("password")
    @classmethod
    def _password(cls, value: SecretStr | None) -> SecretStr | None:
        return None if value is None else validate_password(value)


class AccountResponse(BaseModel):
    """Карточка счёта. Ровно эти поля и никаких других — см. docstring модуля."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    label: str
    is_demo: bool
    color: str
    platform: AccountPlatform
    broker: str | None
    server: str | None
    login: int | None
    currency: str
    account_type: AccountType | None
    server_utc_offset_minutes: int | None
    status: AccountStatus
    status_message: str | None
    last_sync_at: UtcDatetime | None
    last_heartbeat_at: UtcDatetime | None
    collector_id: str | None
    sort_order: int
    created_at: UtcDatetime
    positions_count: int = Field(description="Сколько позиций собрано по этому счёту")

    @classmethod
    def from_account(cls, account: models.TradingAccount, positions_count: int) -> AccountResponse:
        """Сборка по явному списку полей.

        `model_validate(account)` вернул бы сегодня то же самое — ровно до дня, когда
        в модель добавят поле: оно молча наполнилось бы из ORM-объекта. Здесь новое поле
        ответа требует строчки в этом методе, то есть видно в диффе.
        """
        return cls(
            id=account.id,
            label=account.label,
            is_demo=account.is_demo,
            color=account.color,
            platform=account.platform,  # type: ignore[arg-type]
            broker=account.broker,
            server=account.server,
            login=account.login,
            currency=account.currency,
            account_type=account.account_type,  # type: ignore[arg-type]
            server_utc_offset_minutes=account.server_utc_offset_minutes,
            status=account.status,  # type: ignore[arg-type]
            status_message=account.status_message,
            last_sync_at=account.last_sync_at,
            last_heartbeat_at=account.last_heartbeat_at,
            collector_id=account.collector_id,
            sort_order=account.sort_order,
            created_at=account.created_at,
            positions_count=positions_count,
        )


class AccountsResponse(BaseModel):
    """Список счетов.

    Без курсора, в отличие от общего правила SPEC.md 5.1: счетов у пользователя единицы,
    а глобальный переключатель (SPEC.md 9.2) обязан показать все сразу — постраничный
    список заставил бы его крутить цикл ради заведомо одной страницы.
    """

    items: list[AccountResponse]


class SyncNowResponse(BaseModel):
    """Ответ `POST /accounts/{id}/sync-now` (SPEC.md 5.2).

    Это расписка о принятой просьбе, а не результат синка: выполняет его коллектор на
    следующем heartbeat. Поэтому здесь `collector_online` — без него единственное, что
    UI мог бы сказать после нажатия «Синхронизировать», это «готово», и на выключенном
    коллекторе это было бы неправдой ровно до тех пор, пока пользователь не сдастся.
    """

    model_config = ConfigDict(extra="forbid")

    sync_requested_at: UtcDatetime
    last_sync_at: UtcDatetime | None
    last_heartbeat_at: UtcDatetime | None
    collector_online: bool = Field(
        description="Heartbeat коллектора свежее 5 минут. Если нет — просьба ждёт запуска"
    )

    @classmethod
    def accepted(
        cls,
        account: models.TradingAccount,
        *,
        requested_at: datetime,
        collector_online: bool,
    ) -> SyncNowResponse:
        """`requested_at` приходит отдельным аргументом, а не читается из счёта: в модели
        колонка nullable, а в этом ответе — нет, и брать её надо там, где она только что
        записана.
        """
        return cls(
            sync_requested_at=requested_at,
            last_sync_at=account.last_sync_at,
            last_heartbeat_at=account.last_heartbeat_at,
            collector_online=collector_online,
        )


class SyncRunResponse(BaseModel):
    """Строка `sync_runs` (SPEC.md 3.3)."""

    model_config = ConfigDict(extra="forbid")

    id: int
    source: str
    started_at: UtcDatetime
    finished_at: UtcDatetime | None
    deals_received: int | None
    deals_new: int | None
    positions_rebuilt: int | None
    server_utc_offset_minutes: int | None
    error: str | None

    @classmethod
    def from_run(cls, run: ingest_models.SyncRun) -> SyncRunResponse:
        return cls(
            id=run.id,
            source=run.source,
            started_at=run.started_at,
            finished_at=run.finished_at,
            deals_received=run.deals_received,
            deals_new=run.deals_new,
            positions_rebuilt=run.positions_rebuilt,
            server_utc_offset_minutes=run.server_utc_offset_minutes,
            error=run.error,
        )


class SyncRunsResponse(BaseModel):
    items: list[SyncRunResponse]
