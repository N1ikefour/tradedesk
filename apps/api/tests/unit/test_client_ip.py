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
from app.core.config import ConfigError, Settings, get_settings

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


def test_networks_are_refused() -> None:
    """Подсеть опаснее `*` на вид безобиднее: она включает шлюз docker.

    Прогон ревью S0-06 с `10.87.0.0/24` в списке: 12 подделанных адресов напрямую с хоста
    получили 12 отдельных лимитов, то есть лимита не осталось вовсе. Запрос с хоста мимо
    прокси приходит именно со шлюза, и он оказывался «доверенным прокси».
    """
    with pytest.raises(ConfigError) as excinfo:
        parse_trusted_proxies("10.87.0.0/24")

    message = str(excinfo.value)
    assert "10.87.0.0/24" in message
    assert "шлюз" in message


def test_non_ip_in_the_chain_falls_back_to_the_peer() -> None:
    """Значение уходит в ключ Redis: `unknown` и произвольная строка туда попасть не должны."""
    trusted = parse_trusted_proxies(PROXY)

    assert client_ip(make_request(PROXY, "unknown"), trusted) == PROXY
    assert client_ip(make_request(PROXY, "$(whoami)"), trusted) == PROXY
    assert client_ip(make_request(PROXY, "x" * 300), trusted) == PROXY


def test_non_ip_does_not_let_the_walk_continue_leftwards() -> None:
    """Пропустить мусор и взять элемент левее — значит взять то, что прислал клиент."""
    trusted = parse_trusted_proxies(PROXY)

    request = make_request(PROXY, "203.0.113.9, unknown")

    assert client_ip(request, trusted) == PROXY


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
    monkeypatch.setenv("TRUSTED_PROXIES", "10.87.0.10, 10.87.0.11")

    assert bool(trusted_proxies(Settings()))
    check_trusted_proxies(Settings())


def test_gate_refuses_broken_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRUSTED_PROXIES", "*")

    with pytest.raises(ConfigError):
        check_trusted_proxies(Settings())


async def run_startup(env: pytest.MonkeyPatch, make_app: Callable[[], FastAPI], value: str) -> None:
    """Прогоняет старт приложения с заданным TRUSTED_PROXIES.

    Импорт внутри функции и `cache_clear` после него — оба обязательны, и оба про одно:
    `app/main.py` собирает приложение прямо на импорте модуля, а `get_settings` кэширован.
    Импорт на уровне модуля наполнил бы кэш значениями из .env репозитория ещё на сборе
    тестов — то есть раньше, чем отработают модульные фикстуры integration-тестов, и те
    полезли бы в боевую БД вместо тестовой. Без `cache_clear` окружение теста не видно
    вовсе, и результат зависит от того, импортировал ли `app.main` кто-то раньше.
    """
    from app.main import lifespan

    env.setenv("TRUSTED_PROXIES", value)
    get_settings.cache_clear()
    app = make_app()
    async with lifespan(app):
        pass


async def test_startup_warns_when_the_list_is_unset(
    local_env: pytest.MonkeyPatch,
    make_app: Callable[[], FastAPI],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Молчать нельзя: за прокси ненастроенный список делает лимит общим на всю установку.

    Доверять заголовку «на всякий случай» — тем более: это полный обход лимита.
    Остаётся сказать вслух при старте.
    """
    await run_startup(local_env, make_app, "")

    assert "app.trusted_proxies_unset" in capsys.readouterr().out


async def test_startup_is_quiet_when_the_list_is_set(
    local_env: pytest.MonkeyPatch,
    make_app: Callable[[], FastAPI],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Контроль: предупреждение не должно быть фоновым шумом в настроенной установке."""
    await run_startup(local_env, make_app, PROXY)

    output = capsys.readouterr().out
    assert "app.started" in output
    assert "app.trusted_proxies_unset" not in output


async def test_startup_refuses_a_subnet(
    local_env: pytest.MonkeyPatch, make_app: Callable[[], FastAPI]
) -> None:
    """Гейт на старте, а не молчаливая дыра: подсеть в списке роняет запуск."""
    local_env.setenv("TRUSTED_PROXIES", "10.87.0.0/24")
    get_settings.cache_clear()

    with pytest.raises(ConfigError) as excinfo:
        make_app()

    assert "10.87.0.0/24" in str(excinfo.value)
