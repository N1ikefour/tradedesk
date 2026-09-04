"""Адрес клиента за прокси — X-06.

Проверяется ровно то, ради чего заведён `TRUSTED_PROXIES`: заголовок читается только от
доверенного источника, подделка от недоверенного игнорируется, а в цепочке берётся первый
недоверенный справа — не первый и не последний.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi import FastAPI
from starlette.datastructures import Headers
from starlette.requests import Request

from app.core.client_ip import (
    check_trusted_proxies,
    client_ip,
    forwarded_chain,
    parse_trusted_proxies,
    trusted_proxies,
)
from app.core.config import ConfigError, Settings

PROXY = "10.87.0.10"
BROWSER = "203.0.113.7"


def make_request(peer: str | None, forwarded_for: str | None = None) -> Request:
    """ASGI-scope вручную: тестируется чтение scope, а не маршрутизация FastAPI."""
    raw_headers = []
    if forwarded_for is not None:
        raw_headers.append((b"x-forwarded-for", forwarded_for.encode()))
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/auth/request-code",
        "headers": Headers(raw=raw_headers).raw,
        "client": (peer, 51234) if peer else None,
    }
    return Request(scope)


def test_no_trusted_list_ignores_the_header() -> None:
    """Поведение по умолчанию — адрес соединения. Доверять заголовку без списка нельзя."""
    trusted = parse_trusted_proxies("")

    assert client_ip(make_request(PROXY, f"{BROWSER}"), trusted) == PROXY


def test_untrusted_peer_cannot_forge_the_header() -> None:
    """Ровно та подделка, ради которой заведён список: чужой адрес одной строкой."""
    trusted = parse_trusted_proxies(PROXY)

    forged = make_request("198.51.100.1", "1.2.3.4")

    assert client_ip(forged, trusted) == "198.51.100.1"


def test_trusted_proxy_reveals_the_real_client() -> None:
    trusted = parse_trusted_proxies(PROXY)

    assert client_ip(make_request(PROXY, BROWSER), trusted) == BROWSER


def test_chain_takes_first_untrusted_from_the_right() -> None:
    """Слева — то, что прислал клиент; справа — то, что дописали прокси."""
    trusted = parse_trusted_proxies(f"{PROXY}, 10.87.0.11")

    request = make_request(PROXY, f"1.2.3.4, {BROWSER}, 10.87.0.11")

    assert client_ip(request, trusted) == BROWSER


def test_client_supplied_prefix_is_not_taken() -> None:
    """http-proxy дописывает адрес к тому, что прислал клиент: левый элемент — подделка."""
    trusted = parse_trusted_proxies(PROXY)

    request = make_request(PROXY, f"9.9.9.9, {BROWSER}")

    assert client_ip(request, trusted) == BROWSER


def test_trusted_proxy_without_header_falls_back_to_peer() -> None:
    trusted = parse_trusted_proxies(PROXY)

    assert client_ip(make_request(PROXY), trusted) == PROXY


def test_whole_chain_trusted_returns_leftmost() -> None:
    """Клиент сам оказался прокси из списка — брать больше нечего."""
    trusted = parse_trusted_proxies(f"{PROXY}, 10.87.0.11")

    request = make_request(PROXY, "10.87.0.11")

    assert client_ip(request, trusted) == "10.87.0.11"


def test_ports_are_stripped_from_the_chain() -> None:
    assert forwarded_chain(f"{BROWSER}:51234, [2001:db8::1]:8080, 10.0.0.1") == [
        BROWSER,
        "2001:db8::1",
        "10.0.0.1",
    ]


def test_networks_are_supported() -> None:
    trusted = parse_trusted_proxies("10.87.0.0/24")

    assert client_ip(make_request("10.87.0.42", BROWSER), trusted) == BROWSER
    assert client_ip(make_request("10.88.0.42", BROWSER), trusted) == "10.88.0.42"


def test_missing_peer_is_not_a_crash() -> None:
    assert client_ip(make_request(None, BROWSER), parse_trusted_proxies(PROXY)) is None


def test_star_is_refused() -> None:
    """`*` — не «менее строго», а полный обход: любой клиент получает свежий лимит."""
    with pytest.raises(ConfigError) as excinfo:
        parse_trusted_proxies("*")

    assert "TRUSTED_PROXIES" in str(excinfo.value)


def test_garbage_is_refused() -> None:
    """Опечатка в адресе прокси иначе тихо возвращает лимит к общему на всю установку."""
    with pytest.raises(ConfigError) as excinfo:
        parse_trusted_proxies("10.87.0.10, не-адрес")

    assert "не-адрес" in str(excinfo.value)


def test_gate_reads_the_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRUSTED_PROXIES", "10.87.0.10, 10.87.1.0/24")

    assert bool(trusted_proxies(Settings()))
    check_trusted_proxies(Settings())


def test_gate_refuses_broken_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRUSTED_PROXIES", "*")

    with pytest.raises(ConfigError):
        check_trusted_proxies(Settings())


async def test_startup_warns_when_the_list_is_unset(
    local_env: pytest.MonkeyPatch,
    make_app: Callable[[], FastAPI],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Молчать нельзя: за прокси ненастроенный список делает лимит общим на всю установку.

    Доверять заголовку «на всякий случай» — тем более: это полный обход лимита.
    Остаётся сказать вслух при старте.
    """
    from app.main import lifespan

    local_env.setenv("TRUSTED_PROXIES", "")
    app = make_app()

    async with lifespan(app):
        pass

    assert "app.trusted_proxies_unset" in capsys.readouterr().out


async def test_startup_is_quiet_when_the_list_is_set(
    local_env: pytest.MonkeyPatch,
    make_app: Callable[[], FastAPI],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Контроль: предупреждение не должно быть фоновым шумом в настроенной установке."""
    from app.main import lifespan

    local_env.setenv("TRUSTED_PROXIES", PROXY)
    app = make_app()

    async with lifespan(app):
        pass

    output = capsys.readouterr().out
    assert "app.started" in output
    assert "app.trusted_proxies_unset" not in output
