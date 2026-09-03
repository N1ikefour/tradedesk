"""env-guard прода: приложение не стартует на пустых и дефолтных секретах."""

from __future__ import annotations

import pytest

from app.core.config import ConfigError, Settings, check_production_secrets, get_settings


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

    assert presence["SECRET_KEY"] == "present"
    assert presence["MASTER_KEY"] == "MISSING"
    assert "super-secret-value" not in str(presence)


def test_secret_not_leaked_by_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("SECRET_KEY", "super-secret-value")

    settings = get_settings()

    assert "super-secret-value" not in repr(settings)
    assert "super-secret-value" not in str(settings.model_dump())
