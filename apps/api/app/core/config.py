"""Конфигурация приложения: значения только из окружения (SPEC.md 11.2)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import unquote, urlsplit

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# apps/api/app/core/config.py -> core -> app -> api -> apps -> корень репозитория
_REPO_ROOT = Path(__file__).resolve().parents[4]

# Имя параметра с паролем в query-строке соединения: `?password=…` у asyncpg и redis.
_PASSWORD_QUERY_PARAM = "password"

# Плейсхолдеры из шаблонов и туториалов. В проде это «значение не задано».
PLACEHOLDER_SECRET_VALUES = frozenset(
    {"", "…", "...", "change-me", "changeme", "change_me", "secret", "placeholder", "todo", "xxx"}
)


class ConfigError(RuntimeError):
    """Конфигурация непригодна для запуска. Бросается до создания приложения."""


class Settings(BaseSettings):
    """Переменные окружения из `.env.example`. Переменных сверх него быть не должно."""

    model_config = SettingsConfigDict(
        # В Docker переменные приходят из окружения, .env отсутствует — это не ошибка.
        env_file=(_REPO_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["local", "prod"] = "local"
    app_name: str = "TradeDesk"
    app_url: str = "http://localhost:5173"

    # SecretStr: значение не попадает в repr, str и model_dump() модели.
    secret_key: SecretStr = SecretStr("")
    master_key: SecretStr = SecretStr("")
    otp_pepper: SecretStr = SecretStr("")
    collector_token: SecretStr = SecretStr("")

    # В URL хранилищ есть пароль — они тоже секреты.
    database_url: SecretStr = SecretStr("postgresql+asyncpg://td:td@postgres:5432/td")
    redis_url: SecretStr = SecretStr("redis://redis:6379/0")

    email_provider: Literal["console", "resend"] = "console"
    resend_api_key: SecretStr = SecretStr("")
    email_from: str = "TradeDesk <no-reply@example.com>"

    s3_endpoint: str = "http://minio:9000"
    s3_bucket: str = "td"
    s3_access_key: SecretStr = SecretStr("")
    s3_secret_key: SecretStr = SecretStr("")

    sentry_dsn: SecretStr = SecretStr("")

    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"

    def required_secrets(self) -> dict[str, SecretStr]:
        """Секреты, без которых прод не запускается. Имя переменной -> значение."""
        return {
            "SECRET_KEY": self.secret_key,
            "MASTER_KEY": self.master_key,
            "OTP_PEPPER": self.otp_pepper,
            "COLLECTOR_TOKEN": self.collector_token,
        }

    def scrubbable_secret_values(self) -> list[str]:
        """Значения, которые логгер вырезает из любого текста. URL целиком не отдаём —
        в нём есть и полезный для диагностики хост; из URL регистрируется только пароль."""
        values = [secret.get_secret_value() for secret in self.required_secrets().values()]
        values += [
            self.resend_api_key.get_secret_value(),
            self.s3_access_key.get_secret_value(),
            self.s3_secret_key.get_secret_value(),
        ]
        for url in (self.database_url, self.redis_url):
            values += passwords_from_url(url.get_secret_value())
        return [value for value in values if value.strip()]

    def secret_presence(self) -> dict[str, list[str]]:
        """Presence-check для логов: имена секретов, никогда не значения.

        Имя секрета — в значении, а не в ключе: ключ с таким именем цензор логгера режет
        на любой глубине, и presence-блок превратился бы в `{"SECRET_KEY": "***"}`.
        """
        filled = {name: is_secret_filled(value) for name, value in self.required_secrets().items()}
        return {
            "present": [name for name, is_filled in filled.items() if is_filled],
            "missing": [name for name, is_filled in filled.items() if not is_filled],
        }


def passwords_from_url(url: str) -> list[str]:
    """Пароль из connection string: и форма `user:pass@host`, и `?password=…`.

    Регексп логгера режет только первую форму и только внутри URL. Зарегистрированное
    значение вырезается из любого текста — в том числе когда пароль пришёл отдельным словом.
    Возвращаются оба написания: как в URL и после percent-декодирования.
    """
    try:
        parts = urlsplit(url)
        raw_passwords = [parts.password or ""]
        query = parts.query
    except ValueError:
        # Битый URL не должен ронять конфигурацию: до соединения дело всё равно не дойдёт.
        return []
    for pair in query.split("&"):
        name, separator, value = pair.partition("=")
        if separator and name.lower() == _PASSWORD_QUERY_PARAM:
            raw_passwords.append(value)
    passwords: list[str] = []
    for raw in raw_passwords:
        for password in (raw, unquote(raw)):
            if password.strip() and password not in passwords:
                passwords.append(password)
    return passwords


def is_secret_filled(value: SecretStr) -> bool:
    return value.get_secret_value().strip().lower() not in PLACEHOLDER_SECRET_VALUES


def check_production_secrets(settings: Settings) -> None:
    """В проде отказываем в старте на пустых и дефолтных секретах.

    DEVELOPER_MANUAL.md 11.2. В `local` не мешаем: секреты там появляются по мере надобности.
    """
    if not settings.is_prod:
        return
    missing = [
        name for name, value in settings.required_secrets().items() if not is_secret_filled(value)
    ]
    if missing:
        raise ConfigError(
            "APP_ENV=prod: запуск невозможен, не заданы или содержат значение по умолчанию "
            f"переменные окружения: {', '.join(missing)}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Единственная точка чтения конфигурации. Гейт отрабатывает здесь, до первого запроса."""
    settings = Settings()
    check_production_secrets(settings)
    return settings
