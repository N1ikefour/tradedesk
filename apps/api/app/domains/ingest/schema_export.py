"""Сборка `packages/shared-schemas/ingest-deals.schema.json` из моделей `schemas.py`.

Схема — производная от pydantic-моделей, а не вторая рукописная копия контракта:
две копии формы расходятся молча, а тест, сравнивающий два списка полей, написанных
одной рукой, ничего не доказывает. Файл нужен читателям вне Python (советник MQL5,
этап 4) и как предмет ревью в PR, поэтому он коммитится, а не собирается на лету.

Перегенерация:

    cd apps/api && python -m app.domains.ingest.schema_export

Правка файла руками бессмысленна — следующая перегенерация её сотрёт, а до тех пор
`tests/unit/test_ingest_schema_contract.py` красный.

Диалект — draft-07 (SPEC.md 2.1). pydantic отдаёт 2020-12, поэтому здесь выполняется
перевод: `$defs` → `definitions`, и каждое ключевое слово результата сверяется со
словарём draft-07. Это проверка словаря; валидация по метасхеме — в
`tests/unit/test_ingest_schema_contract.py`, потому что валидатор JSON Schema нужен
только тестам и в рантайм-образ не едет.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.domains.ingest.schemas import MAX_DEALS_PER_BATCH, batch_json_schema

DRAFT_07 = "http://json-schema.org/draft-07/schema#"

SCHEMA_TITLE = "TradeDesk — батч ингеста сделок MT5"
SCHEMA_DESCRIPTION = (
    "Тело POST /ingest/deals (SPEC.md 5.3). Собирается из pydantic-моделей "
    "apps/api/app/domains/ingest/schemas.py — руками не правится. "
    f"Батч не длиннее {MAX_DEALS_PER_BATCH} сделок: больший сервер отклоняет с HTTP 413, "
    "и в схеме это не выражено намеренно — 413 про объём работы, а не про форму документа. "
    "Денежные поля и объёмы принимаются числом или строкой; строка предпочтительна, "
    "она доезжает до Decimal вообще без float. Границы numeric(18,2) и numeric(18,8) "
    "выражены только для числовой ветки: сравнить строку с числом JSON Schema не умеет, "
    "поэтому переполнение в строке отсекает уже сервер."
)

# packages/shared-schemas лежит в корне репозитория: app/domains/ingest -> app -> api -> apps.
REPO_ROOT = Path(__file__).resolve().parents[5]
SCHEMA_PATH = REPO_ROOT / "packages" / "shared-schemas" / "ingest-deals.schema.json"

# Словарь draft-07 целиком (spec draft-07, разделы 4-10). Ключ вне набора означает, что
# pydantic выдал слово из 2020-12 — `$defs`, `prefixItems`, `unevaluatedProperties` — и
# опубликованный файл перестал быть draft-07.
DRAFT_07_KEYWORDS = frozenset(
    {
        "$schema",
        "$id",
        "$ref",
        "$comment",
        "title",
        "description",
        "default",
        "readOnly",
        "writeOnly",
        "examples",
        "multipleOf",
        "maximum",
        "exclusiveMaximum",
        "minimum",
        "exclusiveMinimum",
        "maxLength",
        "minLength",
        "pattern",
        "additionalItems",
        "items",
        "maxItems",
        "minItems",
        "uniqueItems",
        "contains",
        "maxProperties",
        "minProperties",
        "required",
        "additionalProperties",
        "definitions",
        "properties",
        "patternProperties",
        "dependencies",
        "propertyNames",
        "const",
        "enum",
        "type",
        "format",
        "contentMediaType",
        "contentEncoding",
        "if",
        "then",
        "else",
        "allOf",
        "anyOf",
        "oneOf",
        "not",
    }
)

# Ключевые слова, значение которых — вложенная схема / список схем / словарь схем.
_SUBSCHEMA = ("items", "additionalItems", "contains", "propertyNames", "if", "then", "else", "not")
_SUBSCHEMA_LIST = ("allOf", "anyOf", "oneOf")
_SUBSCHEMA_MAP = ("properties", "patternProperties", "definitions")

# У этих слов значение всегда число; pydantic отдаёт границы Decimal как float, и 1e+16
# в файле контракта читается хуже, чем целое. Округления тут не происходит: превращение
# делается только тогда, когда float точно равен целому.
_NUMERIC = ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf")


class SchemaExportError(RuntimeError):
    """Сборка схемы не смогла остаться в draft-07."""


def _tidy(node: object) -> object:
    """Канонический вид узла: без `title`, с целыми границами, с отсортированными ключами.

    `title` pydantic выставляет каждому полю («Time Msc»), и для контракта это шум:
    смысл поля несёт `description`, а имя — ключ в `properties`. Ключевые слова внутри
    узла сортируются, а порядок самих `properties` сохраняется: он повторяет порядок
    объявления полей и читается как модель.
    """
    if isinstance(node, list):
        return [_tidy(item) for item in node]
    if not isinstance(node, dict):
        return node

    source: dict[str, Any] = node
    result: dict[str, Any] = {}
    for key in sorted(source):
        if key == "title":
            continue
        value = source[key]
        if key in _SUBSCHEMA_MAP and isinstance(value, dict):
            nested: dict[str, Any] = value
            result[key] = {name: _tidy(sub) for name, sub in nested.items()}
        elif key in _SUBSCHEMA or key in _SUBSCHEMA_LIST:
            result[key] = _tidy(value)
        elif key in _NUMERIC and isinstance(value, float) and value.is_integer():
            result[key] = int(value)
        else:
            result[key] = value

    # В draft-07 `$ref` вытесняет соседей: валидатор их не смотрит. pydantic же кладёт
    # рядом с ним `description`, и в файле она молча ничего не значила бы. Каноническая
    # форма draft-07 — обернуть ссылку в allOf.
    if "$ref" in result and len(result) > 1:
        reference = result.pop("$ref")
        result = {"allOf": [{"$ref": reference}], **result}
    return result


def _walk_keywords(node: object, path: str, seen: list[tuple[str, str, Any]]) -> None:
    """Собирает тройки (путь, ключевое слово, значение) по всем узлам-схемам."""
    if isinstance(node, list):
        for index, item in enumerate(node):
            _walk_keywords(item, f"{path}/{index}", seen)
        return
    if not isinstance(node, dict):
        return
    source: dict[str, Any] = node
    for key, value in source.items():
        seen.append((path, key, value))
        if key in _SUBSCHEMA_MAP and isinstance(value, dict):
            nested: dict[str, Any] = value
            for name, sub in nested.items():
                _walk_keywords(sub, f"{path}/{key}/{name}", seen)
        elif key in _SUBSCHEMA or key in _SUBSCHEMA_LIST:
            _walk_keywords(value, f"{path}/{key}", seen)


def check_draft_07(schema: dict[str, Any]) -> None:
    """Слова — из словаря draft-07, ссылки — на существующие `definitions`.

    Ни одна из двух проверок не заменяет другую. Метасхема (в тесте, на jsonschema)
    проверяет типы значений — что `required` массив уникальных строк, что `pattern`
    компилируется, — но не знает, куда ведут `$ref`. Этот обход знает: висячая ссылка
    и определение, на которое никто не ссылается, ловятся только здесь.
    """
    dialect = schema.get("$schema")
    if dialect != DRAFT_07:
        raise SchemaExportError(f"$schema обязан быть {DRAFT_07}, получено {dialect!r}")

    seen: list[tuple[str, str, Any]] = []
    _walk_keywords(schema, "#", seen)
    unknown = sorted({f"{path}: {key}" for path, key, _ in seen if key not in DRAFT_07_KEYWORDS})
    if unknown:
        raise SchemaExportError("не draft-07: " + ", ".join(unknown))

    definitions: dict[str, Any] = schema.get("definitions", {})
    referenced = {
        str(value).removeprefix("#/definitions/") for _, key, value in seen if key == "$ref"
    }
    missing = sorted(referenced - set(definitions))
    if missing:
        raise SchemaExportError("ссылки в никуда: " + ", ".join(missing))
    unused = sorted(set(definitions) - referenced)
    if unused:
        raise SchemaExportError("определения без ссылок: " + ", ".join(unused))


def build_schema() -> dict[str, Any]:
    """Draft-07 схема батча. Единственный способ получить содержимое файла."""
    generated = batch_json_schema()
    definitions = generated.pop("$defs", {})
    body = _tidy(generated)
    if not isinstance(body, dict):  # pragma: no cover - model_json_schema всегда объект
        raise SchemaExportError("pydantic вернул не объект")

    schema: dict[str, Any] = {"$schema": DRAFT_07, "title": SCHEMA_TITLE}
    schema.update(body)
    # Описание корня — своё, а не docstring модели: он объясняет решения разработчику,
    # а файл читает автор советника, которому нужны правила отправки.
    schema["description"] = SCHEMA_DESCRIPTION
    # Каждое определение приводится к канону отдельно: `definitions` — это словарь имён,
    # а не узел-схема, и пропустить его через `_tidy` целиком значило бы принять имена
    # моделей за ключевые слова и не спуститься внутрь.
    schema["definitions"] = {
        name: _tidy(definition) for name, definition in sorted(definitions.items())
    }
    check_draft_07(schema)
    return schema


def render() -> str:
    """Содержимое файла ровно так, как оно должно лежать в репозитории."""
    return json.dumps(build_schema(), indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    SCHEMA_PATH.write_text(render(), encoding="utf-8")
    print(f"записано: {SCHEMA_PATH}")


if __name__ == "__main__":
    main()
