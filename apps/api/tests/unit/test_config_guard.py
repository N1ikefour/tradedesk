"""env-guard прода: приложение не стартует на пустых и дефолтных секретах."""

from __future__ import annotations

import pytest

from app.core.config import (
    ConfigError,
    Settings,
    check_production_secrets,
    get_settings,
    passwords_from_url,
)


def test_prod_refuses_to_start_without_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "prod")
    for name in ("SECRET_KEY", "MASTER_KEY", "OTP_PEPPER", "COLLECTOR_TOKEN"):
        monkeypatch.setenv(name, "")

    with pytest.raises(ConfigError) as excinfo:
        get_settings()

    message = str(excinfo.value)
    # Сообщение обязано называть переменные: иначе принципалу негде посмотреть, чего не хватает.
    for name in ("SECRET_KEY", "MASTER_KEY", "OTP_PEPPER", "COLLECTOR_TOKEN"):
        assert name in message


def test_prod_refuses_placeholder_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("SECRET_KEY", "change-me")
    monkeypatch.setenv("MASTER_KEY", "real-master-key")
    monkeypatch.setenv("OTP_PEPPER", "real-pepper")
    monkeypatch.setenv("COLLECTOR_TOKEN", "real-token")

    with pytest.raises(ConfigError) as excinfo:
        get_settings()

    assert "SECRET_KEY" in str(excinfo.value)
    assert "MASTER_KEY" not in str(excinfo.value)


def test_local_starts_without_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    for name in ("SECRET_KEY", "MASTER_KEY", "OTP_PEPPER", "COLLECTOR_TOKEN"):
        monkeypatch.setenv(name, "")

    check_production_secrets(Settings())  # не бросает


def test_presence_check_never_returns_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("SECRET_KEY", "super-secret-value")
    monkeypatch.setenv("MASTER_KEY", "")

    presence = get_settings().secret_presence()

    assert "SECRET_KEY" in presence["present"]
    assert "MASTER_KEY" in presence["missing"]
    assert "super-secret-value" not in str(presence)


def test_s3_access_key_is_scrubbable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ключ есть в SECRET_EVENT_KEYS логгера — значит, режется и в свободном тексте."""
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("S3_ACCESS_KEY", "s3-access-key-value")

    assert "s3-access-key-value" in Settings().scrubbable_secret_values()


def test_password_with_percent_encoding_registered_in_both_spellings() -> None:
    """В URL пароль закодирован, в тексте ошибки — уже нет; в логах встречаются оба."""
    passwords = passwords_from_url("postgresql://td:p%40ss-w0rd@db.internal:5432/td")

    assert "p%40ss-w0rd" in passwords
    assert "p@ss-w0rd" in passwords


def test_url_without_password_gives_nothing() -> None:
    assert passwords_from_url("redis://redis:6379/0") == []


def test_broken_url_does_not_break_configuration() -> None:
    """Значения приходят из окружения: разбор URL не должен ронять старт приложения."""
    assert passwords_from_url("postgresql://td:pass@[::1") == []


def test_secret_not_leaked_by_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("SECRET_KEY", "super-secret-value")

    settings = get_settings()

    assert "super-secret-value" not in repr(settings)
    assert "super-secret-value" not in str(settings.model_dump())
