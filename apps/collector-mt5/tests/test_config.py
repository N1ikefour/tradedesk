"""Разбор `collector.env` — SPEC.md 8.1.

Ошибку в этом файле человек допустит один раз, на своей машине, и увидит её только он.
Поэтому проверяется не «настройки прочитались», а то, что каждая кривая строка называет
себя по-русски и что при этом ни в одну ошибку не попадает `COLLECTOR_TOKEN`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from collector import config
from collector.config import CollectorSettings, ConfigError

TOKEN = "collector-token-0123456789"

BASE = {
    "api_url": "http://localhost:8000",
    "collector_token": TOKEN,
    "collector_id": "nikita-laptop",
    "mt5_terminal_exe": "C:\\Program Files\\MetaTrader 5\\terminal64.exe",
    "mt5_portable_root": "C:\\td-terminals",
}


def _settings(**overrides: str) -> CollectorSettings:
    return CollectorSettings(**{**BASE, **overrides})  # type: ignore[arg-type]


def test_defaults_match_the_spec() -> None:
    settings = _settings()
    assert settings.sync_interval_seconds == 60
    assert settings.heartbeat_interval_seconds == 60
    assert settings.first_sync_days == 3650
    assert settings.max_accounts == 3
    assert settings.log_level == "INFO"


def test_api_url_gets_the_version_prefix() -> None:
    """Маршруты API живут за `/api/v1`; в `collector.env` человек пишет адрес без него."""
    assert _settings().api_base_url == "http://localhost:8000/api/v1"


def test_trailing_slash_does_not_double_up() -> None:
    assert (
        _settings(api_url="http://localhost:8000/").api_base_url == "http://localhost:8000/api/v1"
    )


def test_api_url_without_a_scheme_is_refused() -> None:
    with pytest.raises(ValueError, match="http://"):
        _settings(api_url="localhost:8000")


def test_stray_whitespace_in_the_token_is_stripped_like_the_server_does() -> None:
    """Симметрия с `expected_token` в api: иначе пробел даёт токен, который не совпадёт."""
    settings = _settings(collector_token=f"  {TOKEN}  ")
    assert settings.collector_token.get_secret_value() == TOKEN


def test_empty_token_is_refused_at_start_not_at_the_first_request() -> None:
    with pytest.raises(ValueError, match="COLLECTOR_TOKEN"):
        _settings(collector_token="   ")


@pytest.mark.parametrize("bad", ["-starts-with-dash", "имя-по-русски", "with space", "a" * 65])
def test_collector_id_follows_the_same_alphabet_as_the_server(bad: str) -> None:
    """Копия правила границы: кривой идентификатор обязан ловиться здесь, а не в 400."""
    with pytest.raises(ValueError, match="COLLECTOR_ID"):
        _settings(collector_id=bad)


@pytest.mark.parametrize("good", ["nikita-laptop", "win11.home", "a", "srv:1@home"])
def test_valid_collector_ids_pass(good: str) -> None:
    assert _settings(collector_id=good).collector_id == good


def test_token_never_appears_in_the_error_text() -> None:
    """Отчёт об ошибке конфига — ровно то место, где секрет утекает по невнимательности."""
    with pytest.raises(ConfigError) as error:
        config.load_settings(environ={**BASE, "COLLECTOR_ID": "-bad"})
    assert TOKEN not in str(error.value)


def test_secrets_lists_the_token_for_the_log_scrubber() -> None:
    assert _settings().secrets == (TOKEN,)


def test_env_file_is_parsed_with_comments_and_quotes(tmp_path: Path) -> None:
    env = tmp_path / "collector.env"
    env.write_text(
        "\n".join(
            [
                "# комментарий",
                "",
                'API_URL="http://localhost:8000"',
                f"COLLECTOR_TOKEN={TOKEN}",
                "COLLECTOR_ID=nikita-laptop",
                "MT5_TERMINAL_EXE=C:\\Program Files\\MetaTrader 5\\terminal64.exe",
                "MT5_PORTABLE_ROOT=C:\\td-terminals",
                "FIRST_SYNC_DAYS=30",
            ]
        ),
        encoding="utf-8",
    )
    settings = config.load_settings(env)
    assert settings.first_sync_days == 30
    assert settings.api_url == "http://localhost:8000"


def test_missing_env_file_says_what_to_do(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"collector\.env\.example"):
        config.load_settings(tmp_path / "nope.env")


def test_windows_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """SPEC.md 8.3: на macOS и Linux коллектор не запускается и говорит об этом."""
    assert config.platform_refusal("Windows") is None
    refusal = config.platform_refusal("Darwin")
    assert refusal is not None
    assert "только на Windows" in refusal


def test_cyrillic_path_is_flagged_but_not_forbidden() -> None:
    """X-43: у первого пользователя папка профиля кириллицей, а MetaTrader5 — нативный код.

    Запрет был бы выдумкой — работает такой путь или нет, мы не проверяли. Предупреждение
    честнее: оно попадёт в лог рядом с настоящей ошибкой, если она случится.
    """
    warning = config.non_ascii_path_warning(Path("C:\\Users\\Никита\\MetaTrader 5"))
    assert warning is not None
    assert "латиницы" in warning
    assert config.non_ascii_path_warning(Path("C:\\td-terminals")) is None


def test_log_dir_defaults_to_the_working_folder() -> None:
    assert _settings().log_dir == Path("logs")
