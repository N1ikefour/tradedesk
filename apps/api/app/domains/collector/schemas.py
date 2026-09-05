"""Тела запросов и ответов коллектора — SPEC.md 5.3 и 5.6.

⚠️ `AssignmentResponse` — **единственная модель ответа во всём API, содержащая пароль
счёта** (`CLAUDE.md` §5). Поэтому она собирается полем за полем в `issued`, как
`AccountResponse.from_account`, и её состав заморожен тестом
`tests/unit/test_collector_contract.py`: любое новое поле здесь обязано пройти через
правку теста, то есть через ревью.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal, get_args
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

from app.core.schemas import UtcDatetime
from app.core.text import MAX_EXTERNAL_TEXT_LENGTH
from app.domains.accounts.models import TradingAccount
from app.domains.accounts.schemas import AccountStatus

# Словарь состояний из SPEC.md 5.3. Что каждое из них делает со статусом счёта —
# `accounts.service.apply_heartbeat`; совпадение множеств закрыто тестом.
CollectorState = Literal["running", "error", "stopped"]
COLLECTOR_STATES: tuple[str, ...] = get_args(CollectorState)

COLLECTOR_ID_MAX_LENGTH = 64

# Закрытый алфавит, а не свободная строка. `collector_id` уезжает в
# `trading_accounts.collector_id`, а оттуда — в `AccountResponse` каждого маршрута счетов,
# то есть на все экраны (X-21, второй канал). Скраб такой канал только сужает; закрытый
# алфавит закрывает его целиком, и имени машины или UUID он не мешает.
COLLECTOR_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:@-]*$"
_COLLECTOR_ID_RE = re.compile(COLLECTOR_ID_PATTERN)

COLLECTOR_ID_ERROR = (
    "collector_id: латиница, цифры и символы . _ - : @, "
    f"первый символ — буква или цифра, не длиннее {COLLECTOR_ID_MAX_LENGTH} символов"
)

# Больше счетов, чем помещается в один терминал на одной машине (SPEC.md 8.2, MAX_ACCOUNTS),
# в heartbeat прийти не может. Предел стоит затем, чтобы обладатель токена не заставлял
# сервер разбирать список произвольной длины.
MAX_HEARTBEAT_ACCOUNTS = 200
# Сообщение об ошибке от коллектора. Хранится урезанным до MAX_EXTERNAL_TEXT_LENGTH
# (X-21), но отвергать heartbeat из-за длинного текста нельзя — счёт остался бы без
# признака поломки вовсе. Здесь только потолок, за которым это уже не сообщение.
MESSAGE_MAX_LENGTH = 1000

DUPLICATE_ACCOUNTS_ERROR = "Счёт указан в heartbeat дважды: какое из состояний верное — неизвестно"
MESSAGE_TOO_LONG_ERROR = f"message не длиннее {MESSAGE_MAX_LENGTH} символов"
TERMINAL_LOGIN_ERROR = "terminal_login — целое положительное число"


def validate_collector_id(value: str) -> str:
    collector_id = value.strip()
    if not collector_id or len(collector_id) > COLLECTOR_ID_MAX_LENGTH:
        raise PydanticCustomError("collector_id", COLLECTOR_ID_ERROR)
    if _COLLECTOR_ID_RE.match(collector_id) is None:
        raise PydanticCustomError("collector_id", COLLECTOR_ID_ERROR)
    return collector_id


# Одна проверка на оба входа: тело heartbeat и query-параметр assignments. Через
# `AfterValidator`, а не через `Query(pattern=…)`, ради русского текста ошибки
# (SPEC.md 5.1): встроенное ограничение pydantic отвечает по-английски.
CollectorId = Annotated[str, AfterValidator(validate_collector_id)]


class HeartbeatAccount(BaseModel):
    """Состояние одного счёта в heartbeat."""

    model_config = ConfigDict(extra="forbid")

    account_id: UUID
    state: CollectorState = Field(description="Состояние процесса, следящего за счётом")
    message: str | None = Field(
        default=None,
        description=(
            "Причина при state=error. Показывается пользователю, поэтому обязана быть "
            f"понятным текстом; хранится урезанной до {MAX_EXTERNAL_TEXT_LENGTH} символов"
        ),
    )
    # Принимается, но не сохраняется: колонки под него нет, а заводить её ради значения
    # без потребителя — миграция впустую. Поле объявлено потому, что SPEC.md 5.3 кладёт
    # его в тело, а модель закрыта `extra="forbid"`: без объявления heartbeat коллектора
    # отвергался бы целиком.
    terminal_login: int | None = Field(
        default=None, description="Номер счёта, под которым коллектор вошёл в терминал"
    )

    @field_validator("message")
    @classmethod
    def _message(cls, value: str | None) -> str | None:
        if value is not None and len(value) > MESSAGE_MAX_LENGTH:
            raise PydanticCustomError("message", MESSAGE_TOO_LONG_ERROR)
        return value

    @field_validator("terminal_login", mode="before")
    @classmethod
    def _terminal_login_is_not_bool(cls, value: object) -> object:
        # В Python bool наследует int, и мягкий режим pydantic пропустил бы `true` молча.
        if isinstance(value, bool):
            raise PydanticCustomError("terminal_login", TERMINAL_LOGIN_ERROR)
        return value

    @field_validator("terminal_login")
    @classmethod
    def _terminal_login(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if value < 1:
            raise PydanticCustomError("terminal_login", TERMINAL_LOGIN_ERROR)
        return value


class HeartbeatRequest(BaseModel):
    """Тело `POST /ingest/heartbeat` (SPEC.md 5.3)."""

    model_config = ConfigDict(extra="forbid")

    collector_id: CollectorId = Field(description="Идентификатор установки коллектора")
    accounts: list[HeartbeatAccount] = Field(
        default_factory=list,
        max_length=MAX_HEARTBEAT_ACCOUNTS,
        description="Пустой список — коллектор жив, но счетов у него нет",
    )

    @model_validator(mode="after")
    def _accounts_are_unique(self) -> HeartbeatRequest:
        """Дубль счёта в одном батче — ошибка отправителя, а не «побеждает последний».

        Молча применить последнее вхождение значит сделать результат зависящим от
        порядка в списке: `running` и `error` для одного счёта дали бы разный статус
        в зависимости от того, что коллектор положил вторым.
        """
        seen = {account.account_id for account in self.accounts}
        if len(seen) != len(self.accounts):
            raise PydanticCustomError("accounts", DUPLICATE_ACCOUNTS_ERROR)
        return self


class HeartbeatResponse(BaseModel):
    """Сколько счетов heartbeat применил и сколько пропустил.

    Пропущенные — это чужие, несуществующие и выведенные из работы (`paused`,
    `archived`). Счётчик, а не список: коллектор знает, что отправлял, а расхождение
    ему нужно только как признак «спроси assignments заново».
    """

    model_config = ConfigDict(extra="forbid")

    accepted: int
    ignored: int


class AssignmentResponse(BaseModel):
    """Задание коллектору на один счёт — SPEC.md 5.6. **Содержит пароль.**"""

    model_config = ConfigDict(extra="forbid")

    account_id: UUID
    server: str
    login: int
    password: str = Field(
        # `repr=False` — то же решение, что у `service.Assignment`, и по той же причине.
        # Модель собирает роутер, а значит она лежит в кадрах FastAPI при сериализации
        # ответа: любое исключение оттуда печатает кадр, а `scrub_unserializable` вырезает
        # только **известные** секреты, и пароля счёта среди них нет. Защита обязана стоять
        # на обоих объектах пути — асимметрия закреплена тестом.
        repr=False,
        description=(
            "Пароль инвестора. Единственный ответ API, где он есть; в пользовательские "
            "маршруты не попадает никогда"
        ),
    )
    sync_requested_at: UtcDatetime | None = Field(
        description="Просьба пользователя о внеочередном синке (SPEC.md 5.2)"
    )
    last_sync_at: UtcDatetime | None
    status: AccountStatus

    @classmethod
    def issued(cls, account: TradingAccount, password: str) -> AssignmentResponse:
        """Сборка по явному списку полей — тот же приём, что в `AccountResponse`.

        `server` и `login` в модели счёта nullable (у csv и manual их нет), а здесь
        обязательны. Сужение делает выборка `service.assignable`; проверка ниже — её
        страховка на случай, если условие оттуда однажды уедет.
        """
        if account.server is None or account.login is None:
            raise ValueError(f"счёт {account.id} без server/login не может быть заданием")
        return cls(
            account_id=account.id,
            server=account.server,
            login=account.login,
            password=password,
            sync_requested_at=account.sync_requested_at,
            last_sync_at=account.last_sync_at,
            status=account.status,  # type: ignore[arg-type]
        )


class AssignmentListResponse(BaseModel):
    """Конверт выдачи — SPEC.md 5.6.

    Не голый массив: в него нечего добавить, не сломав потребителя, а курсорная пагинация
    из SPEC.md 5.1 однажды потребует именно добавления поля рядом с `items`. Потребитель
    (`S1-08`) ещё не написан — момент, когда это стоит ноль. Ту же форму отдаёт
    `GET /accounts`.
    """

    model_config = ConfigDict(extra="forbid")

    items: list[AssignmentResponse]
