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

`*` как значение запрещено: это то же самое, что доверять заголовку без списка.
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
_IpNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network


class TrustedProxies:
    """Разобранный `TRUSTED_PROXIES`: адреса и подсети, чьему `X-Forwarded-For` мы верим."""

    def __init__(self, addresses: frozenset[_IpAddress], networks: tuple[_IpNetwork, ...]) -> None:
        self._addresses = addresses
        self._networks = networks

    def __bool__(self) -> bool:
        return bool(self._addresses or self._networks)

    def __contains__(self, host: str | None) -> bool:
        if not host:
            return False
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            # Не IP: unix-сокет, имя хоста. Доверять тому, что нельзя сверить, нечего.
            return False
        if address in self._addresses:
            return True
        return any(address in network for network in self._networks)


@lru_cache(maxsize=8)
def parse_trusted_proxies(raw: str) -> TrustedProxies:
    """`"10.87.0.10, 10.87.1.0/24"` -> `TrustedProxies`. Пустая строка — пустой список.

    Мусор в значении — отказ, а не молчаливое сужение списка: опечатка в адресе прокси
    иначе тихо возвращает лимит к общему на всю установку.
    """
    addresses: set[_IpAddress] = set()
    networks: list[_IpNetwork] = []
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
        try:
            if "/" in entry:
                networks.append(ipaddress.ip_network(entry, strict=False))
            else:
                addresses.add(ipaddress.ip_address(entry))
        except ValueError as exc:
            raise ConfigError(
                f"TRUSTED_PROXIES: {entry!r} не разбирается как IP-адрес или подсеть ({exc})"
            ) from exc
    return TrustedProxies(frozenset(addresses), tuple(networks))


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
    """Адрес клиента: из `X-Forwarded-For`, если соединение пришло от доверенного прокси."""
    peer = request.client.host if request.client else None
    if not trusted or peer not in trusted:
        return peer
    header = request.headers.get(FORWARDED_FOR_HEADER)
    if not header:
        return peer
    chain = forwarded_chain(header)
    for host in reversed(chain):
        if host not in trusted:
            return host
    # Вся цепочка доверенная: клиент и сам оказался прокси из списка.
    return chain[0] if chain else peer
