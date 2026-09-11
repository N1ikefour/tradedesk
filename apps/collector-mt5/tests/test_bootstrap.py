"""Сборка `collector.env` при первом запуске — S1-10.

Проверяется то, что человек увидит на своей машине: файл появился, токен в нём тот
самый, а на экране его нет. Последнее — не украшение: вывод первого запуска уходит в
`logs/run-collector.log`, и напечатанный там токен пережил бы установку навсегда.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from collector import bootstrap
from collector.config import load_settings

TOKEN = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"

APP_ENV = f"""
# .env установки TradeDesk
APP_ENV=local
SECRET_KEY=не-этот-ключ-нужен
COLLECTOR_TOKEN={TOKEN}
POSTGRES_PASSWORD=и-не-этот
"""

EXAMPLE = """# образец
API_URL=http://localhost:8000
COLLECTOR_TOKEN=
COLLECTOR_ID=nikita-laptop
"""


def _example_file(tmp_path: Path, text: str = EXAMPLE) -> Path:
    path = tmp_path / "collector.env.example"
    path.write_text(text, encoding="utf-8")
    return path


def _app_env_file(tmp_path: Path, text: str = APP_ENV) -> Path:
    path = tmp_path / ".env"
    path.write_text(text, encoding="utf-8")
    return path


def test_token_is_carried_over_from_the_installation(tmp_path: Path) -> None:
    env_file = tmp_path / "collector.env"

    outcome = bootstrap.ensure_env_file(
        env_file=env_file,
        example_file=_example_file(tmp_path),
        app_env_file=_app_env_file(tmp_path),
    )

    assert bootstrap.parse_env(env_file.read_text(encoding="utf-8"))["COLLECTOR_TOKEN"] == TOKEN
    assert outcome.exit_code == bootstrap.EXIT_OK


def test_a_freshly_created_file_does_not_stop_the_run_any_more(tmp_path: Path) -> None:
    """X-66: решений, которые человек принимал в этом файле, больше нет.

    Останов был нужен ради `MT5_TERMINAL_EXE` и `MAX_ACCOUNTS`; терминал теперь открывает
    человек, и синхронизируется тот счёт, который открыт. Требовать второй запуск ради
    ничего — значит учить человека проходить мимо текста на экране.
    """
    outcome = bootstrap.ensure_env_file(
        env_file=tmp_path / "collector.env",
        example_file=_example_file(tmp_path),
        app_env_file=_app_env_file(tmp_path),
    )

    assert outcome.exit_code == bootstrap.EXIT_OK
    text = "\n".join(outcome.lines)
    assert "MetaTrader 5" in text
    assert "войдите в счёт" in text


def test_a_file_created_without_a_token_still_stops_the_run(tmp_path: Path) -> None:
    """Без токена коллектор получит 401 и напишет на карточке «TradeDesk не отвечает»."""
    outcome = bootstrap.ensure_env_file(
        env_file=tmp_path / "collector.env",
        example_file=_example_file(tmp_path),
        app_env_file=tmp_path / "missing.env",
    )

    assert outcome.exit_code == bootstrap.EXIT_NEEDS_HUMAN
    assert "COLLECTOR_TOKEN" in "\n".join(outcome.lines)


def test_the_token_never_reaches_the_screen(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Вывод первого запуска уходит в файл лога (`run-collector.bat --service`)."""
    env_file = tmp_path / "collector.env"

    bootstrap.main(
        [
            "--env-file",
            str(env_file),
            "--example",
            str(_example_file(tmp_path)),
            "--app-env",
            str(_app_env_file(tmp_path)),
        ]
    )

    printed = capsys.readouterr().out
    assert TOKEN not in printed
    assert TOKEN in env_file.read_text(encoding="utf-8")


def test_an_existing_file_is_never_rewritten(tmp_path: Path) -> None:
    """Чужой файл — чужой: правка настроек человека здесь была бы сюрпризом."""
    env_file = tmp_path / "collector.env"
    original = "API_URL=http://localhost:9000\nCOLLECTOR_TOKEN=свой-токен\nMAX_ACCOUNTS=4\n"
    env_file.write_text(original, encoding="utf-8")

    outcome = bootstrap.ensure_env_file(
        env_file=env_file,
        example_file=_example_file(tmp_path),
        app_env_file=_app_env_file(tmp_path),
    )

    assert env_file.read_text(encoding="utf-8") == original
    assert outcome.exit_code == bootstrap.EXIT_OK


def test_an_existing_file_without_a_token_says_where_to_take_it(tmp_path: Path) -> None:
    env_file = tmp_path / "collector.env"
    env_file.write_text("COLLECTOR_TOKEN=\n", encoding="utf-8")
    app_env = _app_env_file(tmp_path)

    outcome = bootstrap.ensure_env_file(
        env_file=env_file,
        example_file=_example_file(tmp_path),
        app_env_file=app_env,
    )

    assert outcome.exit_code == bootstrap.EXIT_NEEDS_HUMAN
    assert str(app_env) in "\n".join(outcome.lines)


def test_installation_without_env_names_the_missing_file(tmp_path: Path) -> None:
    """`.env` установки нет — коллектор всё равно ставится, но говорит, чего не хватает."""
    env_file = tmp_path / "collector.env"
    missing = tmp_path / "нет-такого" / ".env"

    outcome = bootstrap.ensure_env_file(
        env_file=env_file,
        example_file=_example_file(tmp_path),
        app_env_file=missing,
    )

    assert env_file.exists()
    assert outcome.exit_code == bootstrap.EXIT_NEEDS_HUMAN
    assert str(missing) in "\n".join(outcome.lines)


def test_installation_env_without_a_token_is_not_silent(tmp_path: Path) -> None:
    outcome = bootstrap.ensure_env_file(
        env_file=tmp_path / "collector.env",
        example_file=_example_file(tmp_path),
        app_env_file=_app_env_file(tmp_path, "APP_ENV=local\nCOLLECTOR_TOKEN=\n"),
    )

    assert "COLLECTOR_TOKEN" in "\n".join(outcome.lines)
    assert outcome.exit_code == bootstrap.EXIT_NEEDS_HUMAN


def test_a_missing_example_names_the_broken_installation(tmp_path: Path) -> None:
    outcome = bootstrap.ensure_env_file(
        env_file=tmp_path / "collector.env",
        example_file=tmp_path / "collector.env.example",
        app_env_file=_app_env_file(tmp_path),
    )

    assert outcome.exit_code == bootstrap.EXIT_NEEDS_HUMAN
    assert "collector.env.example" in "\n".join(outcome.lines)


def test_only_empty_values_are_filled(tmp_path: Path) -> None:
    """Значение, уже стоящее в образце, — решение автора образца, а не пустое место."""
    filled, taken = bootstrap.fill_example(
        "COLLECTOR_TOKEN=уже-стоит\n", {"COLLECTOR_TOKEN": TOKEN}
    )

    assert taken == ()
    assert TOKEN not in filled


def test_nothing_but_the_token_travels_between_files() -> None:
    """Из `.env` установки берётся один ключ, а не всё подряд из чужого файла."""
    filled, taken = bootstrap.fill_example(
        "API_URL=\nCOLLECTOR_TOKEN=\n",
        {"COLLECTOR_TOKEN": TOKEN, "API_URL": "http://ушло-бы-сюда"},
    )

    assert taken == ("COLLECTOR_TOKEN",)
    assert "ушло-бы-сюда" not in filled


def test_env_parsing_survives_comments_quotes_and_blank_lines() -> None:
    values = bootstrap.parse_env('\n# комментарий\n\nA="1"\nb = 2 \nсломанная строка\n')

    assert values == {"A": "1", "B": "2"}


def test_the_real_example_produces_settings_the_collector_accepts(tmp_path: Path) -> None:
    """Главный тест модуля: собранный файл читается `config.load_settings` без правок.

    Образец и разбор настроек живут в разных задачах (`S1-08` и эта), и разъехаться им
    ничто не мешает: `collector.env.example` — обычный текст, который никто не исполняет.
    Здесь берётся настоящий файл образца, а не выдуманный.
    """
    example = Path(__file__).resolve().parents[1] / "collector.env.example"
    env_file = tmp_path / "collector.env"

    bootstrap.ensure_env_file(
        env_file=env_file, example_file=example, app_env_file=_app_env_file(tmp_path)
    )
    settings = load_settings(env_file)

    assert settings.collector_token.get_secret_value() == TOKEN
    assert settings.api_url == "http://localhost:8000"
    assert str(settings.state_dir) == "state"
