"""HTTP к TradeDesk: assignments, батч сделок, heartbeat.

Три маршрута, все за сервисным токеном (`SPEC.md` §5.3, §5.6). Разбор ответа и решение
«повторять или сдаваться» вынесены в чистые функции — их видно тестами; сетевая часть
остаётся тонкой.

**Пароль счёта приходит именно сюда** — `GET /internal/collector/assignments` единственный
ответ API, который его содержит (`CLAUDE.md` §5). Отсюда два следствия. `Assignment.password`
объявлен с `repr=False`: объект попадает в кадры стека, а кадры печатаются при любом
падении. И конструктор `Assignment` вносит пароль в скраб логов — это единственная точка,
где значение появляется в процессе, поэтому здесь защита включается на все пути сразу.

Ретраи — `tenacity` с потолком. Потолок обязателен: недоступность API не имеет права
превратиться ни в бесконечный цикл, ни в потерю данных. Потери и не будет — следующая
итерация синка заберёт то же окно заново (`sync.py`).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from types import TracebackType
from typing import Any, Final

import httpx
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_delay,
    wait_exponential,
)

from collector import logging_setup, messages
from collector.config import CollectorSettings

REQUEST_TIMEOUT_SECONDS: Final = 60.0
# Потолок ретраев одного вызова. Меньше интервала синка нет смысла ставить, больше —
# опасно: процесс перестал бы отвечать на heartbeat и выглядел бы зависшим.
RETRY_BUDGET_SECONDS: Final = 120.0
RETRY_FIRST_WAIT_SECONDS: Final = 1.0
RETRY_MAX_WAIT_SECONDS: Final = 20.0

RETRYABLE_STATUSES: Final = frozenset({408, 425, 429, 500, 502, 503, 504})


class ApiError(Exception):
    """Отказ API, который повторять бесполезно: тело, токен, счёт."""

    def __init__(self, message: str, *, code: str = "", status: int = 0) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.message = message


class RetryableApiError(Exception):
    """Временный отказ: сеть, 5xx, 429. Повторяется в пределах бюджета."""


@dataclass(frozen=True)
class Assignment:
    """Задание на один счёт — `SPEC.md` §5.6. **Содержит пароль инвестора.**"""

    account_id: str
    server: str
    login: int
    # `repr=False` — то же решение и по той же причине, что у `AssignmentResponse` в api:
    # печать объекта в трейсбеке не имеет права вынести пароль в лог.
    password: str = field(repr=False)
    sync_requested_at: datetime | None
    last_sync_at: datetime | None
    status: str

    def __post_init__(self) -> None:
        """Появился объект с паролем — значит, скраб обязан знать это значение.

        Регистрация стоит в конструкторе, а не у вызывающего, потому что это **точка
        входа пароля в процесс**: другого способа получить его нет. Любой будущий
        потребитель assignments (менеджер процессов `S1-09`) получает защиту, не зная о
        ней, а «забыли зарегистрировать» перестаёт быть возможным диффом.
        """
        logging_setup.register_secret(self.password)


@dataclass(frozen=True)
class IngestResult:
    """Ответ `POST /ingest/deals` (`SPEC.md` §5.3, пункт 7)."""

    received: int
    inserted: int
    duplicates: int
    positions_rebuilt: int
    sync_run_id: str


def is_retryable(status: int) -> bool:
    """Стоит ли повторять запрос с таким кодом ответа.

    4xx, кроме перечисленных, — наша ошибка: кривое тело, чужой токен, архивный счёт.
    Повтор такого запроса ничего не чинит, а только скрывает причину за таймаутами.
    """
    return status in RETRYABLE_STATUSES


def error_from_response(status: int, body: str) -> ApiError:
    """Тело ошибки API (`SPEC.md` §5.1) → исключение с человекочитаемым текстом.

    Ответ разбирается терпимо: за прокси между коллектором и API может оказаться что
    угодно, включая HTML страницы ошибки. Тогда в текст уходит код статуса — этого
    достаточно, чтобы человек понял, куда смотреть.
    """
    code, message = "", ""
    try:
        parsed: Any = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        parsed = None
    if isinstance(parsed, dict):
        error = parsed.get("error")
        if isinstance(error, dict):
            code = str(error.get("code") or "")
            message = str(error.get("message") or "")
    if not message:
        message = f"HTTP {status}"
    return ApiError(message, code=code, status=status)


def parse_assignments(payload: object) -> list[Assignment]:
    """Конверт `{items: [...]}` → задания. Форма конверта закреплена в `SPEC.md` §5.6."""
    if not isinstance(payload, dict):
        raise ApiError("TradeDesk вернул не тот ответ на запрос заданий коллектора")
    items = payload.get("items")
    if not isinstance(items, list):
        raise ApiError("В ответе на запрос заданий коллектора нет списка items")
    return [_assignment(item) for item in items]


def _assignment(item: object) -> Assignment:
    if not isinstance(item, dict):
        raise ApiError("Задание коллектора пришло не объектом")
    try:
        return Assignment(
            account_id=str(item["account_id"]),
            server=str(item["server"]),
            login=int(item["login"]),
            password=str(item["password"]),
            sync_requested_at=_moment(item.get("sync_requested_at")),
            last_sync_at=_moment(item.get("last_sync_at")),
            status=str(item.get("status") or ""),
        )
    except (KeyError, TypeError, ValueError) as error:
        # Текст исключения не подставляется: в `item` лежит пароль, и `KeyError` от
        # словаря печатает ключ, а `ValueError` от `int()` — значение.
        raise ApiError(
            "Задание коллектора пришло в неожиданном виде: нет обязательного поля "
            "или время без часового пояса"
        ) from error


def _moment(value: object) -> datetime | None:
    """ISO 8601 с `Z` (`SPEC.md` §5.1) → `datetime` с зоной.

    Зона обязательна, и проверка на неё не формальность: наивное время из этого ответа
    уезжает в `sync.terminal_bounds`, а там `_naive` трактует его через `astimezone`,
    то есть как локальное время машины пользователя. Сегодня такого не бывает — контракт
    api отдаёт `Z`, — но в самом коллекторе это не заперто ничем.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("время не строкой")
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        raise ValueError("время без часового пояса")
    return moment


def parse_ingest_result(payload: object) -> IngestResult:
    if not isinstance(payload, dict):
        raise ApiError("TradeDesk вернул не тот ответ на батч сделок")
    try:
        return IngestResult(
            received=int(payload["received"]),
            inserted=int(payload["inserted"]),
            duplicates=int(payload["duplicates"]),
            positions_rebuilt=int(payload["positions_rebuilt"]),
            sync_run_id=str(payload["sync_run_id"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ApiError("Ответ на батч сделок пришёл без обязательных полей") from error


@dataclass(frozen=True)
class HeartbeatAccount:
    """Состояние одного счёта для `POST /ingest/heartbeat` (`SPEC.md` §5.3)."""

    account_id: str
    state: str
    message: str | None = None
    terminal_login: int | None = None

    def payload(self) -> dict[str, Any]:
        body: dict[str, Any] = {"account_id": self.account_id, "state": self.state}
        if self.message is not None:
            # Скраб на втором канале, которым текст уходит из процесса. Сообщение
            # собирается из текста терминала, а он для нас чужой: `CLAUDE.md` §5 требует,
            # чтобы пароля не было и в текстах ошибок, а `status_message` видно на экране.
            body["message"] = messages.fit(
                logging_setup.scrub_text(self.message, logging_setup.known_secrets())
            )
        if self.terminal_login is not None:
            body["terminal_login"] = self.terminal_login
        return body


class ApiClient:
    """Тонкий клиент. Всё, что решает, — в чистых функциях выше."""

    def __init__(
        self,
        settings: CollectorSettings,
        *,
        client: httpx.Client | None = None,
        retry_budget_seconds: float = RETRY_BUDGET_SECONDS,
        retry_max_wait_seconds: float = RETRY_MAX_WAIT_SECONDS,
    ) -> None:
        self._settings = settings
        self._retry_budget_seconds = retry_budget_seconds
        self._retry_max_wait_seconds = retry_max_wait_seconds
        self._client = client or httpx.Client(
            base_url=settings.api_base_url,
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={
                "Authorization": f"Bearer {settings.collector_token.get_secret_value()}",
                "Content-Type": "application/json",
            },
        )

    def __enter__(self) -> ApiClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def assignments(self, collector_id: str) -> list[Assignment]:
        payload = self._request(
            "GET", "/internal/collector/assignments", params={"collector_id": collector_id}
        )
        return parse_assignments(payload)

    def send_deals(self, batch: dict[str, Any]) -> IngestResult:
        return parse_ingest_result(self._request("POST", "/ingest/deals", json=batch))

    def heartbeat(self, collector_id: str, accounts: Iterable[HeartbeatAccount]) -> None:
        body = {
            "collector_id": collector_id,
            "accounts": [account.payload() for account in accounts],
        }
        self._request("POST", "/ingest/heartbeat", json=body)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> object:
        """Один вызов API с ретраями. Исчерпанный бюджет — обычный `ApiError`.

        Наружу выходит один тип отказа: вызывающему нечего решать по поводу того, была
        причина временной или нет, — он в любом случае доложит человеку и попробует на
        следующей итерации синка.
        """
        try:
            for attempt in self._retrying():
                with attempt:
                    return self._once(method, path, params=params, json=json)
        except RetryableApiError as error:
            raise ApiError(str(error)) from error
        raise ApiError(f"Не удалось выполнить {method} {path}")  # pragma: no cover

    def _once(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None,
        json: dict[str, Any] | None,
    ) -> object:
        try:
            response = self._client.request(method, path, params=params, json=json)
        except httpx.HTTPError as error:
            raise RetryableApiError(
                messages.API_UNREACHABLE.format(
                    api_url=self._settings.api_url, reason=type(error).__name__
                )
            ) from error
        if is_retryable(response.status_code):
            raise RetryableApiError(
                messages.API_UNREACHABLE.format(
                    api_url=self._settings.api_url, reason=f"HTTP {response.status_code}"
                )
            )
        if response.status_code >= 400:
            raise error_from_response(response.status_code, response.text)
        return _decode(response)

    def _retrying(self) -> Retrying:
        return Retrying(
            stop=stop_after_delay(self._retry_budget_seconds),
            wait=wait_exponential(
                multiplier=RETRY_FIRST_WAIT_SECONDS, max=self._retry_max_wait_seconds
            ),
            retry=retry_if_exception_type(RetryableApiError),
            reraise=True,
        )


def _decode(response: httpx.Response) -> object:
    try:
        return response.json()
    except (json.JSONDecodeError, ValueError) as error:
        raise ApiError("TradeDesk ответил не JSON — проверьте адрес API_URL") from error
