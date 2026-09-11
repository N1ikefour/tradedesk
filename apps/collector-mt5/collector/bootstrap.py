"""Сборка `collector.env` при первом запуске — `SPEC.md` §8.1, задача `S1-10`.

Файл настроек человек собирает ровно один раз, и ровно здесь ошибается дороже всего:
`COLLECTOR_TOKEN` лежит в `.env` установки, его надо найти, скопировать без опечатки и
не перепутать с `SECRET_KEY`, который лежит строкой выше. Ошибка при этом не называет
себя: коллектор стартует, получает `401` и пишет на карточку счёта, что TradeDesk не
отвечает. Поэтому перенос делает `run-collector.bat` этим модулем, а не человек глазами.

Переносится **только** `COLLECTOR_TOKEN`. Остальное в примере уже верно: `API_URL`
указывает на тот же `localhost:8000`, что публикует compose, а `LOG_DIR` и `STATE_DIR`
относительны папке установки.

⚠️ **Первый запуск больше не останавливается, если токен доехал** (`X-66`). Останов был
нужен ради двух решений человека — `MT5_TERMINAL_EXE` и `MAX_ACCOUNTS`, — и оба поля из
настроек ушли: терминал открывает человек, и синхронизируется тот счёт, который открыт.
Спрашивать стало нечего, а требовать второй запуск ради ничего — значит учить человека
проходить мимо текста на экране.

Тексты живут в этом модуле, а не в `messages.py`: там потолок 200 символов, потому что
каждая строка оттуда уезжает в `status_message` карточки счёта. Здесь — консоль первого
запуска, и ограничение у неё другое: человек читает её один раз и по ней действует.

⚠️ Значение токена не печатается никогда и ни при какой ошибке (`CLAUDE.md` §5): вывод
этого модуля под Планировщиком заданий уходит в файл `logs/run-collector.log`.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

TOKEN_KEY: Final = "COLLECTOR_TOKEN"

# Что переносится из `.env` установки. Список закрытый: каждое значение здесь — секрет
# или адрес, который человек иначе копирует руками, а не всё подряд из чужого файла.
INHERITED_KEYS: Final[tuple[str, ...]] = (TOKEN_KEY,)

EXIT_OK: Final = 0
EXIT_NEEDS_HUMAN: Final = 2

ENV_CREATED: Final = "Создан файл настроек {path}"

TOKEN_TAKEN: Final = "COLLECTOR_TOKEN перенесён из {source} — вписывать его руками не нужно."

TOKEN_MISSING: Final = (
    "COLLECTOR_TOKEN перенести не удалось: {reason}\n"
    "Откройте {env} в Блокноте, найдите строку COLLECTOR_TOKEN= и скопируйте её значение "
    "в такую же строку файла {path}."
)

OPEN_THE_TERMINAL: Final = (
    "Дальше нужен MetaTrader 5: откройте терминал и войдите в счёт.\n"
    "Коллектор синхронизирует тот счёт, который открыт в терминале, и ждёт остальные, "
    "пока вы в них не войдёте. Пароль счёта коллектору не нужен."
)

TOKEN_EMPTY_IN_EXISTING: Final = (
    "В файле {path} пустая строка COLLECTOR_TOKEN — коллектор не сможет войти в TradeDesk."
)

NO_EXAMPLE: Final = (
    "Не найден образец настроек {path}. Установка распакована не целиком: "
    "распакуйте архив релиза заново."
)

APP_ENV_MISSING: Final = (
    "файл установки {path} не найден — TradeDesk на этой машине ещё не настроен"
)

APP_ENV_WITHOUT_TOKEN: Final = "в файле {path} нет заполненной строки COLLECTOR_TOKEN"

ENV_READY: Final = "Настройки {path} на месте."


@dataclass(frozen=True)
class Outcome:
    """Что сделано с `collector.env` и что осталось человеку."""

    lines: tuple[str, ...]
    exit_code: int


def parse_env(text: str) -> dict[str, str]:
    """`KEY=value` построчно. Правила те же, что у `config._read_env_file`.

    Второй разбор вместо переиспользования — потому что тот читает путь, а сюда текст
    приходит уже прочитанным: файл установки может быть недоступен, и это не исключение,
    а обычная ветка с объяснением человеку.
    """
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator:
            continue
        values[key.strip().upper()] = value.strip().strip('"').strip("'")
    return values


def fill_example(example: str, source: Mapping[str, str]) -> tuple[str, tuple[str, ...]]:
    """Подставить в образец значения из `.env` установки. Возвращает текст и что взято.

    Строка образца с уже непустым значением не трогается: правка чужого решения — не то,
    чего ждут от подстановки токена.
    """
    taken: list[str] = []
    lines = example.splitlines()
    for index, raw in enumerate(lines):
        key, separator, value = raw.partition("=")
        name = key.strip().upper()
        if not separator or name not in INHERITED_KEYS or value.strip():
            continue
        replacement = source.get(name, "").strip()
        if not replacement:
            continue
        lines[index] = f"{key}={replacement}"
        taken.append(name)
    text = "\n".join(lines)
    return (text if text.endswith("\n") else text + "\n"), tuple(taken)


def ensure_env_file(*, env_file: Path, example_file: Path, app_env_file: Path) -> Outcome:
    """Довести `collector.env` до состояния, в котором коллектор имеет смысл запускать.

    Токен доехал — запуск продолжается: решений, которые надо было бы принять человеку в
    этом файле, больше не осталось (`X-66`). Не доехал — остановка: без токена коллектор
    получит `401` и напишет на карточке счёта, что TradeDesk не отвечает.
    """
    if env_file.exists():
        return _existing(env_file, app_env_file)
    if not example_file.exists():
        return Outcome((NO_EXAMPLE.format(path=example_file),), EXIT_NEEDS_HUMAN)

    source, reason = _app_env_values(app_env_file)
    content, taken = fill_example(example_file.read_text(encoding="utf-8"), source)
    env_file.write_text(content, encoding="utf-8")

    lines = [ENV_CREATED.format(path=env_file)]
    if TOKEN_KEY not in taken:
        lines.append(TOKEN_MISSING.format(reason=reason, env=app_env_file, path=env_file))
        return Outcome(tuple(lines), EXIT_NEEDS_HUMAN)
    lines.append(TOKEN_TAKEN.format(source=app_env_file))
    lines.append(OPEN_THE_TERMINAL)
    return Outcome(tuple(lines), EXIT_OK)


def _existing(env_file: Path, app_env_file: Path) -> Outcome:
    """Файл уже есть. Чужой файл не переписывается — только читается и оценивается."""
    values = parse_env(env_file.read_text(encoding="utf-8"))
    if values.get(TOKEN_KEY, "").strip():
        return Outcome((ENV_READY.format(path=env_file),), EXIT_OK)
    _, reason = _app_env_values(app_env_file)
    return Outcome(
        (
            TOKEN_EMPTY_IN_EXISTING.format(path=env_file),
            TOKEN_MISSING.format(reason=reason, env=app_env_file, path=env_file),
        ),
        EXIT_NEEDS_HUMAN,
    )


def _app_env_values(app_env_file: Path) -> tuple[dict[str, str], str]:
    """Значения из `.env` установки и причина, если взять их не вышло."""
    if not app_env_file.exists():
        return {}, APP_ENV_MISSING.format(path=app_env_file)
    values = parse_env(app_env_file.read_text(encoding="utf-8", errors="replace"))
    if not values.get(TOKEN_KEY, "").strip():
        return values, APP_ENV_WITHOUT_TOKEN.format(path=app_env_file)
    return values, ""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="collector.bootstrap",
        description="Первый запуск: собрать collector.env из образца и .env установки",
    )
    parser.add_argument("--env-file", type=Path, required=True, help="Путь к collector.env")
    parser.add_argument("--example", type=Path, required=True, help="Путь к collector.env.example")
    parser.add_argument(
        "--app-env", type=Path, required=True, help="Путь к .env установки TradeDesk"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    outcome = ensure_env_file(
        env_file=args.env_file, example_file=args.example, app_env_file=args.app_env
    )
    for line in outcome.lines:
        print(line)
    return outcome.exit_code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
