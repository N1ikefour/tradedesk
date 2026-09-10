"""Чей счёт открыт в терминале — и наш ли это счёт. `X-66`, `T-07`.

Модуль существует потому, что коллектор больше **не входит** в терминал: терминал
открывает человек, а `mt5.initialize()` без пути подключается к тому экземпляру, который
найдёт на машине. Библиотека при этом не спрашивает, чей счёт нам нужен, и не сообщает,
что подключила не тот, — она просто отдаёт историю того счёта, в который человек вошёл.

Отсюда правило, ради которого модуль и написан: **пока не доказано, что в терминале
открыт именно ожидаемый счёт, ни одна сделка не уезжает.** Цена ошибки в другую сторону
несимметрична и необратима: сделки чужого счёта попадут в чужой журнал молча, а `deals` —
append-only факты, и вынуть их обратно нечем (`CLAUDE.md` §2).

Функции здесь чистые, и это не стиль, а способ проверки: `mt5_client.py` на машине
разработки не выполняется ни разу, поэтому решение «наш это счёт или нет» обязано жить
там, где его видит тест.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class OpenAccount:
    """Кто открыт в терминале прямо сейчас — по ответу `account_info()`."""

    login: int
    server: str


@dataclass(frozen=True)
class Watched:
    """Счёт, за которым коллектору поручено следить, — по ответу assignments."""

    account_id: str
    login: int
    server: str


MatchStatus = Literal[
    "match",  # логин и сервер совпали ровно у одного счёта: его и синхронизируем
    "server_mismatch",  # логин совпал, сервер нет — синхронизировать нельзя, но причина видна
    "ambiguous",  # подошло больше одного счёта: выбирать наугад нельзя
    "unknown_account",  # такого логина среди наших счетов нет вовсе
]


@dataclass(frozen=True)
class Match:
    """Что коллектор вправе делать с открытым счётом и что сказать человеку.

    `account_id` заполнен у `match` и `server_mismatch`: во втором случае сообщение о
    расхождении принадлежит именно этому счёту, а не всем сразу.
    """

    status: MatchStatus
    account_id: str | None = None
    expected_server: str = ""


class HasIdentity(Protocol):
    """Та часть `account_info()`, по которой счёт опознают."""

    login: int
    server: str


def read_open_account(info: HasIdentity) -> OpenAccount | None:
    """Кто открыт в терминале. `None` — библиотека ответила не тем, чем обещала.

    Библиотека обещает целое в `login`, но обещание непроверяемое: терминала на машине
    разработки нет. `None` вместо исключения потому, что у двух вызывающих разный
    правильный ответ на одно и то же: подключению нужен текст человеку, а сторожу второй
    сверки — «доказать, что счёт тот же, не удалось», то есть выбросить батч.
    """
    login = getattr(info, "login", None)
    if not isinstance(login, int) or isinstance(login, bool):
        return None
    return OpenAccount(login=login, server=str(getattr(info, "server", "")))


def normalize_server(name: str) -> str:
    """Имя сервера брокера для сравнения: без регистра, без краевых пробелов.

    Больше ничего не выбрасывается — ни дефисы, ни пробелы внутри. «EGlobalTrade-Demo» и
    «E-Global-Trade Demo» вполне могут оказаться разными серверами одного брокера, и
    решать это за человека нельзя: он видит имя в терминале и пишет его в карточку счёта.
    """
    return name.strip().casefold()


def same_server(left: str, right: str) -> bool:
    return normalize_server(left) == normalize_server(right)


def match_open_account(open_account: OpenAccount, watched: Sequence[Watched]) -> Match:
    """Какой из наших счетов открыт в терминале.

    Сначала ищется полное совпадение — логин **и** сервер. Только если его нет, отдельно
    ищется совпадение по логину: это отказ, а не разрешение, но отказ с точной причиной.

    Почему сервер обязателен. Номер счёта уникален у своего брокера, а не во всём мире:
    демо-серверы разных брокеров выдают номера из одинаковых диапазонов, и совпадение
    только по логину означало бы, что демо-счёт 293272 у одного брокера может уехать в
    журнал демо-счёта 293272 у другого. Проверка обоих полей стоит один `if`, а её
    отсутствие — необратимо испорченный журнал.

    **Двух подошедших счетов достаточно, чтобы не синхронизировать ни одного.** Взять
    первый значило бы, что выбор делает порядок ответа assignments: один и тот же счёт
    попадал бы то в один журнал, то в другой, и человек об этом не узнал бы никогда. А
    завести два таких счёта нетрудно — уникальность в БД сравнивает имя сервера
    посимвольно, здесь же оно сравнивается без регистра, так что «E-Global-Real» и
    «e-global-real» с одним логином для базы разные, а для терминала один и тот же.
    """
    exact = [
        candidate.account_id
        for candidate in watched
        if candidate.login == open_account.login
        and same_server(candidate.server, open_account.server)
    ]
    if len(exact) > 1:
        return Match(status="ambiguous")
    if exact:
        return Match(status="match", account_id=exact[0])
    by_login = [candidate for candidate in watched if candidate.login == open_account.login]
    if len(by_login) > 1:
        return Match(status="ambiguous")
    if by_login:
        return Match(
            status="server_mismatch",
            account_id=by_login[0].account_id,
            expected_server=by_login[0].server,
        )
    return Match(status="unknown_account")


def stayed_the_same(before: OpenAccount, after: OpenAccount) -> bool:
    """Тот же счёт в терминале, что и до чтения истории.

    Вторая сверка нужна потому, что человек вправе переключить счёт в любой момент, в том
    числе между `history_deals_get` и отправкой батча. Первая проверка доказывает, чей
    счёт мы **спросили**, вторая — чей счёт нам **ответил**.
    """
    return before.login == after.login and same_server(before.server, after.server)
