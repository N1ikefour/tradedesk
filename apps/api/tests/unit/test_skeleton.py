"""Тривиальный тест каркаса: pytest без единого теста выходит с кодом 5 и красит CI."""

import app


def test_app_package_importable() -> None:
    assert app.__name__ == "app"
