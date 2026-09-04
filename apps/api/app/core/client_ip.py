"""Адрес клиента, когда перед API стоит прокси — X-06.

Лимит «10 запросов кода в час на IP» (SPEC.md 4) осмыслен только на настоящем адресе
клиента. Адрес TCP-соединения им перестаёт быть, как только между браузером и API
появляется посредник: в профиле `local` это vite, в `prod` — caddy. Все пользователи
приходят с одного адреса, и лимит становится общим на всю установку — ревью S0-04
прогнало 12 пользователей с одного адреса и получило блокировку одиннадцатого
**пользователя**.

Голое чтение `X-Forwarded-For` эту дыру не закрывает, а открывает вторую: заголовок
ставит кто угодно, и лимит обходится одной строкой. Поэтому заголовок читается **только
когда соединение пришло от адреса из `TRUSTED_PROXIES`**. Список не задан — работаем по
адресу соединения, как раньше, и предупреждаем в логе при старте.

Цепочку `X-Forwarded-For` каждый прокси **дополняет справа**, а клиент волен прислать
её непустой. Значит слева стоит то, что придумал клиент, а справа — то, что дописали
прокси. Берём первый недоверенный элемент справа: последний адрес, за который ручается
доверенная цепочка. Ни первый (подделывается), ни последний (это сам прокси) не подходят.

⚠️ Принимаются только **точные адреса**. Подсети запрещены наравне с `*`, и это не
перестраховка: в нашей топологии прокси стоит на фиксированном адресе, а подсеть compose
включает шлюз docker — то есть адрес, с которого приходит **любой** запрос с хоста в обход
прокси. Прогон ревью S0-06 с `TRUSTED_PROXIES=10.87.0.0/24`: 12 подделанных адресов прямо
с хоста получили 12 отдельных лимитов. Понадобится пул адресов — это отдельное решение
с ADR, а не строчка в примере конфигурации.
"""

from __future__ import annotations

import ipaddress
from functools import lru_cache
from typing import Final

from starlette.requests import Request

from app.core.config import ConfigError, Settings

FORWARDED_FOR_HEADER: Final = "x-forwarded-for"

TRUST_EVERYTHING = "*"

_IpAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


def _parse_ip(value: str) -> _IpAddress | None:
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        return None


class TrustedProxies:
    """Разобранный `TRUSTED_PROXIES`: адреса, чьему `X-Forwarded-For` мы верим."""

    def __init__(self, addresses: frozenset[_IpAddress]) -> None:
        self._addresses = addresses

    def __bool__(self) -> bool:
        return bool(self._addresses)

    def __contains__(self, host: str | None) -> bool:
        if not host:
            return False
        address = _parse_ip(host)
        # Не IP: unix-сокет, имя хоста, мусор из заголовка. Доверять тому, что нельзя
        # сверить с адресом соединения, нечему.
        return address is not None and address in self._addresses


@lru_cache(maxsize=8)
def parse_trusted_proxies(raw: str) -> TrustedProxies:
    """`"10.87.0.10, 10.87.0.11"` -> `TrustedProxies`. Пустая строка — пустой список.

    Мусор, `*` и подсети — отказ, а не молчаливое сужение списка: опечатка в адресе прокси
    иначе тихо возвращает лимит к общему на всю установку, а подсеть — снимает его вовсе.
    """
    addresses: set[_IpAddress] = set()
    for item in raw.replace(";", ",").split(","):
        entry = item.strip()
        if not entry:
            continue
        if entry == TRUST_EVERYTHING:
            raise ConfigError(
                "TRUSTED_PROXIES='*' запрещено: доверять X-Forwarded-For от любого источника "
                "означает, что лимит по IP обходится подстановкой заголовка. "
                "Укажите конкретные адреса прокси или оставьте переменную пустой."
            )
        if "/" in entry:
            raise ConfigError(
                f"TRUSTED_PROXIES: подсеть {entry!r} запрещена, нужен точный адрес прокси. "
                "Подсеть окружения включает шлюз docker, то есть адрес, с которого приходит "
                "любой запрос с хоста мимо прокси, — и заголовок X-Forwarded-For от него "
                "становится подделываемым. Прокси в docker-compose.yml стоят на "
                "фиксированных адресах именно поэтому."
            )
        address = _parse_ip(entry)
        if address is None:
            raise ConfigError(f"TRUSTED_PROXIES: {entry!r} не разбирается как IP-адрес прокси")
        addresses.add(address)
    return TrustedProxies(frozenset(addresses))


def trusted_proxies(settings: Settings) -> TrustedProxies:
    return parse_trusted_proxies(settings.trusted_proxies)


def check_trusted_proxies(settings: Settings) -> None:
    """Гейт старта: непригодный `TRUSTED_PROXIES` — отказ, а не тихий возврат к общему лимиту."""
    trusted_proxies(settings)


def _host_only(entry: str) -> str:
    """`1.2.3.4:5678` -> `1.2.3.4`, `[::1]:8080` -> `::1`. Порт в цепочке нам не нужен."""
    value = entry.strip()
    if value.startswith("["):
        closing = value.find("]")
        return value[1:closing] if closing > 0 else value
    # Ровно одно двоеточие — это IPv4 с портом; несколько — «голый» IPv6 без скобок.
    if value.count(":") == 1:
        return value.split(":", 1)[0]
    return value


def forwarded_chain(header: str) -> list[str]:
    """Элементы `X-Forwarded-For` слева направо, без портов и пустых значений."""
    return [host for host in (_host_only(item) for item in header.split(",")) if host]


def client_ip(request: Request, trusted: TrustedProxies) -> str | None:
    """Адрес клиента: из `X-Forwarded-For`, если соединение пришло от доверенного прокси.

    Возвращается всегда либо разобранный IP, либо адрес соединения. Значение уходит в ключ
    Redis, а содержимое заголовка пишет клиент: без разбора в ключ уехали бы `unknown`
    и строка произвольной длины. Неразбираемый элемент — повод не верить цепочке целиком,
    а не повод пропустить его и пойти дальше влево.
    """
    peer = request.client.host if request.client else None
    if not trusted or peer not in trusted:
        return peer
    header = request.headers.get(FORWARDED_FOR_HEADER)
    if not header:
        return peer
    chain = forwarded_chain(header)
    candidate = next((host for host in reversed(chain) if host not in trusted), None)
    if candidate is None:
        # Вся цепочка доверенная: клиент и сам оказался прокси из списка.
        candidate = chain[0] if chain else None
    return candidate if candidate is not None and _parse_ip(candidate) else peer
