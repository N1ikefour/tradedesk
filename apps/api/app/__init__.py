"""Пакет приложения TradeDesk API."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("tradedesk-api")
except PackageNotFoundError:  # пакет не установлен (запуск из исходников без pip install -e)
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
