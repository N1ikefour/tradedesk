"""Конфигурация коллектора — SPEC.md 8.1.

Состав полей задан спекой и повторён в `collector.env.example`. Проверки здесь стоят
жёстче, чем нужно самому коллектору, ровно по одной причине: ошибку в `collector.env`
человек допустит один раз и увидит её на своей машине, а не у нас. Пусть она называется
словами при старте, а не превращается в `400` от API через минуту работы.

⚠️ `extra="ignore"` здесь работает как совместимость с уже собранными `collector.env`.
`X-66` убрал три поля — `MT5_TERMINAL_EXE`, `MT5_PORTABLE_ROOT` и `MAX_ACCOUNTS`: терминал
коллектор больше не запускает и копий не делает, а счёт синхронизируется тот, который
открыт, то есть ровно один. Файл первого пользователя эти строки содержит, и падать из-за
них коллектор не имеет права — они просто перестают что-либо значить.
"""

from __future__ import annotations

import platform
import re
from pathlib import Path
from typing import Any, Final, Literal

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from collector import messages

WINDOWS: Final = "Windows"

# Тот же алфавит, что у `COLLECTOR_ID_PATTERN` на границе API
# (`app/domains/collector/schemas.py`). Копия намеренная: коллектор обязан отказать сам,
# а не узнавать о кривом идентификаторе из 400 в ответ на каждый heartbeat.
COLLECTOR_ID_PATTERN: Final = r"^[A-Za-z0-9][A-Za-z0-9._:@-]*$"
COLLECTOR_ID_MAX_LENGTH: Final = 64
_COLLECTOR_ID_RE: Final = re.compile(COLLECTOR_ID_PATTERN)

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]

DEFAULT_ENV_FILENAME: Final = "collector.env"


class ConfigError(Exception):
    """Человекочитаемая причина, по которой коллектор не может стартовать."""


class CollectorSettings(BaseSettings):
    """`collector.env` в терминах программы."""

    model_config = SettingsConfigDict(
        env_file=None,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    api_url: str = Field(description="Базовый адрес TradeDesk без /api/v1")
    collector_token: SecretStr = Field(description="COLLECTOR_TOKEN, тот же, что в .env api")
    collector_id: str = Field(description="Имя этой установки коллектора")
    sync_interval_seconds: int = Field(default=60, ge=5, le=3600)
    heartbeat_interval_seconds: int = Field(default=60, ge=5, le=3600)
    first_sync_days: int = Field(default=3650, ge=1, le=7300)
    log_level: LogLevel = "INFO"
    # Сверх SPEC.md 8.1, со значением по умолчанию: под Task Scheduler (S1-10) рабочей
    # папкой процесса легко оказывается системный каталог, куда писать нельзя. Поле
    # необязательное — `collector.env` без него работает ровно как в спеке.
    log_dir: Path = Field(default=Path("logs"), description="Папка для файлов лога")
    # Единственное, что коллектор помнит между запусками, — смещение часов брокера
    # (`state.py`). До `X-66` файл лежал рядом с портабельной копией терминала, в
    # `MT5_PORTABLE_ROOT`; копий больше нет, а место для кэша нужно.
    state_dir: Path = Field(default=Path("state"), description="Папка для файла состояния")

    @field_validator("api_url")
    @classmethod
    def _api_url(cls, value: str) -> str:
        url = value.strip().rstrip("/")
        if not url.startswith(("http://", "https://")):
            raise ValueError("API_URL начинается с http:// или https://")
        return url

    @field_validator("collector_token")
    @classmethod
    def _collector_token(cls, value: SecretStr) -> SecretStr:
        # `.strip()` симметрично тому, что делает API (`expected_token`): случайный пробел
        # в конце строки .env иначе даёт токен, который не совпадёт никогда.
        token = value.get_secret_value().strip()
        if not token:
            raise ValueError("COLLECTOR_TOKEN пуст — возьмите значение из .env приложения")
        return SecretStr(token)

    @field_validator("collector_id")
    @classmethod
    def _collector_id(cls, value: str) -> str:
        collector_id = value.strip()
        if not collector_id or len(collector_id) > COLLECTOR_ID_MAX_LENGTH:
            raise ValueError(
                "COLLECTOR_ID: от 1 до "
                f"{COLLECTOR_ID_MAX_LENGTH} символов латиницы, цифр и . _ - : @"
            )
        if _COLLECTOR_ID_RE.match(collector_id) is None:
            raise ValueError(
                "COLLECTOR_ID: латиница, цифры и символы . _ - : @, первый символ — буква или цифра"
            )
        return collector_id

    @property
    def api_base_url(self) -> str:
        """Адрес с префиксом версии: маршруты API живут за `/api/v1` (`main.py`)."""
        return f"{self.api_url}/api/v1"

    @property
    def secrets(self) -> tuple[str, ...]:
        """Значения, которых не должно быть ни в логе, ни в тексте ошибки."""
        return (self.collector_token.get_secret_value(),)


def load_settings(
    env_file: Path | None = None, *, environ: dict[str, str] | None = None
) -> CollectorSettings:
    """Прочитать `collector.env`; при ошибке — `ConfigError` с русским текстом."""
    values: dict[str, Any] = dict(_read_env_file(env_file)) if env_file else {}
    if environ is not None:
        values.update({key.lower(): value for key, value in environ.items()})
    try:
        return CollectorSettings(**values)
    except ValidationError as error:
        raise ConfigError(messages.CONFIG_INVALID.format(problems=describe(error))) from error


def describe(error: ValidationError) -> str:
    """`ValidationError` pydantic → одна строка на русском, без значений полей.

    Значения не подставляются намеренно: в `collector.env` лежит `COLLECTOR_TOKEN`, и
    отчёт об ошибке — ровно то место, где секрет утекает в лог по невнимательности.
    """
    problems = []
    for item in error.errors():
        location = ".".join(str(part) for part in item["loc"]) or "значение"
        problems.append(f"{location.upper()}: {item['msg']}")
    return "; ".join(problems)


def _read_env_file(path: Path) -> dict[str, str]:
    """Минимальный разбор `KEY=value`: комментарии, пустые строки, кавычки по краям."""
    if not path.exists():
        raise ConfigError(f"Не найден файл настроек {path}. Скопируйте collector.env.example.")
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator:
            continue
        values[key.strip().lower()] = value.strip().strip('"').strip("'")
    return values


def platform_refusal(system: str | None = None) -> str | None:
    """`None` — можно работать. Строка — почему нельзя (SPEC.md 8.3)."""
    name = platform.system() if system is None else system
    if name == WINDOWS:
        return None
    return messages.not_windows(name or "эта система")


def non_ascii_path_warning(path: Path) -> str | None:
    """Предупреждение о пути вне латиницы — `None`, если путь безопасен (X-43)."""
    text = str(path)
    if text.isascii():
        return None
    return messages.non_ascii_path(text)
