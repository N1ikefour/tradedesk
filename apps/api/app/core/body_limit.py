"""Потолок на размер тела запроса — до разбора JSON.

Лимит `SPEC.md` 5.3 («не больше 5000 сделок → 413») считается по **разобранной** модели:
числа сделок в заголовках нет. Значит без потолка на байты любой отправитель заставляет
сервер разобрать тело произвольного объёма, и лимит по числу сделок от этого не спасает —
это записано в `domains/ingest/schemas.py` (`S1-01`) как долг перед `S1-04`.

Тело читается FastAPI **раньше**, чем решаются зависимости маршрута, поэтому ни проверкой
в маршруте, ни `Depends` этого не сделать: к моменту, когда сработала бы авторизация,
байты уже приняты. Отсюда ASGI-мидлварь — единственный слой, стоящий перед чтением.

Мидлварь узкая по построению: она сторожит **перечисленные пути**, а не всё приложение.
Один общий потолок пришлось бы ставить по самому щедрому потребителю, и загрузка вложений
(`S2-04`, файлы в мегабайтах) подняла бы его и для ингеста — то есть сняла бы защиту
ровно там, где она заведена. Свой путь — свой потолок.

`Content-Length` проверяется первым как дешёвый отсев, но одним им обойтись нельзя:
на `Transfer-Encoding: chunked` заголовка нет вовсе. Поэтому тело всё равно вычитывается
со счётчиком и отдаётся приложению из буфера — расход памяти ограничен самим потолком.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import CODE_BY_STATUS, MESSAGE_BY_STATUS, error_payload
from app.core.logging import get_logger

log = get_logger(__name__)

PAYLOAD_TOO_LARGE_CODE = CODE_BY_STATUS[413]
PAYLOAD_TOO_LARGE_MESSAGE = MESSAGE_BY_STATUS[413]

_JSON_HEADERS = [(b"content-type", b"application/json")]


class BodySizeLimitMiddleware:
    """Отвечает `413` раньше, чем тело дойдёт до разбора. Ровно на заданных путях.

    Реализована как чистая ASGI-мидлварь, а не `BaseHTTPMiddleware`: последняя оборачивает
    запрос в `Request` и сама тянет тело, то есть встаёт уже после того, от чего защищает.
    """

    def __init__(self, app: ASGIApp, *, max_bytes: int, paths: Sequence[str]) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.paths = frozenset(paths)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") not in self.paths:
            await self.app(scope, receive, send)
            return

        declared = _declared_length(scope)
        if declared is not None and declared > self.max_bytes:
            await self._refuse(scope, send, size=declared)
            return

        buffered, received = await _drain(receive, self.max_bytes)
        if received > self.max_bytes:
            await self._refuse(scope, send, size=received)
            return

        await self.app(scope, _replay(buffered), send)

    async def _refuse(self, scope: Scope, send: Send, *, size: int) -> None:
        # Размер и путь — не секрет, содержимое тела в лог не идёт ни в каком виде.
        log.warning(
            "api.body_too_large",
            path=scope.get("path"),
            limit_bytes=self.max_bytes,
            received_bytes=size,
        )
        body = error_payload(
            PAYLOAD_TOO_LARGE_CODE,
            PAYLOAD_TOO_LARGE_MESSAGE,
            {"limit_bytes": self.max_bytes},
        )
        await _send_json(send, 413, body)


def _declared_length(scope: Scope) -> int | None:
    for name, value in scope.get("headers", ()):
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None


async def _drain(receive: Receive, max_bytes: int) -> tuple[list[Message], int]:
    """Вычитывает тело, считая байты. Прекращает, как только потолок превышен.

    Возвращает сами сообщения, а не склеенные байты: приложение получит их обратно
    ровно теми же кусками, включая `http.disconnect`, если он пришёл.
    """
    messages: list[Message] = []
    received = 0
    while True:
        message = await receive()
        messages.append(message)
        if message["type"] != "http.request":
            return messages, received
        received += len(message.get("body", b""))
        if received > max_bytes:
            return messages, received
        if not message.get("more_body", False):
            return messages, received


def _replay(messages: list[Message]) -> Receive:
    """Отдаёт приложению вычитанные сообщения; дальше — пустое тело.

    Хвост нужен затем, что читатель вправе позвать `receive()` ещё раз после последнего
    куска: без ответа он повис бы навсегда.
    """
    pending = list(messages)

    async def receive() -> Message:
        if pending:
            return pending.pop(0)
        return {"type": "http.request", "body": b"", "more_body": False}

    return receive


async def _send_json(send: Send, status_code: int, body: dict[str, object]) -> None:
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status_code,
            "headers": [*_JSON_HEADERS, (b"content-length", str(len(payload)).encode("ascii"))],
        }
    )
    await send({"type": "http.response.body", "body": payload})
