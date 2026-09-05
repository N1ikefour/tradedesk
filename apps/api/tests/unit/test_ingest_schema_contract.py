"""Соответствие `ingest-deals.schema.json` моделям и диалекту draft-07 (S1-01).

Тест не сравнивает два списка полей, написанных одной рукой: он пересобирает файл из
моделей и сверяет его с тем, что лежит в репозитории. Любое расхождение — лишнее поле
в схеме, забытая перегенерация, правка файла руками — делает его красным.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from app.domains.ingest import schema_export
from app.domains.ingest.schema_export import (
    DRAFT_07,
    DRAFT_07_KEYWORDS,
    SCHEMA_PATH,
    SchemaExportError,
    build_schema,
    check_draft_07,
    render,
)
from app.domains.ingest.schemas import ServerTime, batch_json_schema

REGENERATE = "cd apps/api && python -m app.domains.ingest.schema_export"

server_time = TypeAdapter(ServerTime)


@pytest.fixture
def committed() -> str:
    return SCHEMA_PATH.read_text(encoding="utf-8")


@pytest.fixture
def document(committed: str) -> dict[str, Any]:
    parsed: dict[str, Any] = json.loads(committed)
    return parsed


# --- схема и модели ---------------------------------------------------------------


def test_committed_schema_matches_the_models(committed: str) -> None:
    assert committed == render(), (
        "packages/shared-schemas/ingest-deals.schema.json разошёлся с моделями "
        f"app/domains/ingest/schemas.py. Перегенерировать: {REGENERATE}"
    )


def test_extra_model_field_breaks_the_match(
    monkeypatch: pytest.MonkeyPatch, committed: str
) -> None:
    """Проверка того, что предыдущий тест вообще способен покраснеть.

    Модель обзаводится полем, файл остаётся прежним — сравнение обязано разойтись.
    Без этого «схема совпадает с моделями» доказывало бы только то, что обе стороны
    берутся из одного вызова.
    """

    def with_extra_field() -> dict[str, Any]:
        generated = batch_json_schema()
        generated["properties"]["collector_id"] = {"type": "string"}
        generated["required"].append("collector_id")
        return generated

    monkeypatch.setattr(schema_export, "batch_json_schema", with_extra_field)

    assert render() != committed


def test_render_is_deterministic() -> None:
    """Файл коммитится, поэтому его содержимое не должно плясать от прогона к прогону."""
    assert render() == render()


def test_schema_file_lives_in_shared_schemas() -> None:
    assert SCHEMA_PATH.parts[-2:] == ("shared-schemas", "ingest-deals.schema.json")


def test_file_ends_with_a_newline(committed: str) -> None:
    assert committed.endswith("}\n")


def test_only_the_root_keeps_a_title(document: dict[str, Any]) -> None:
    """`title` у каждого поля — след pydantic («Time Msc»), а не часть контракта.

    Тест ловит не косметику, а недоход канонизации до узла: определения один раз уже
    оставались нетронутыми целиком, и заметно это было именно по уцелевшим `title`.
    """
    nodes: list[dict[str, Any]] = []
    _collect_objects(document, nodes)

    assert [node for node in nodes[1:] if "title" in node] == []


# --- диалект ----------------------------------------------------------------------


def test_committed_schema_is_draft_07(document: dict[str, Any]) -> None:
    assert document["$schema"] == DRAFT_07
    check_draft_07(document)


def test_build_schema_checks_itself() -> None:
    """`build_schema` не отдаёт результат, не проверив словарь: сборка и проверка едины."""
    check_draft_07(build_schema())


@pytest.mark.parametrize(
    "keyword",
    ["$defs", "prefixItems", "unevaluatedProperties", "dependentRequired", "$dynamicRef"],
)
def test_keywords_from_2020_12_are_rejected(keyword: str) -> None:
    """Проверка словаря обязана ловить то, ради чего она есть: слова не из draft-07."""
    assert keyword not in DRAFT_07_KEYWORDS

    broken = {"$schema": DRAFT_07, "properties": {"x": {keyword: {}}}}

    with pytest.raises(SchemaExportError, match="не draft-07"):
        check_draft_07(broken)


def test_dangling_ref_is_rejected() -> None:
    broken = {"$schema": DRAFT_07, "properties": {"x": {"$ref": "#/definitions/Missing"}}}

    with pytest.raises(SchemaExportError, match="ссылки в никуда"):
        check_draft_07(broken)


def test_wrong_dialect_is_rejected() -> None:
    with pytest.raises(SchemaExportError, match=r"\$schema"):
        check_draft_07({"$schema": "https://json-schema.org/draft/2020-12/schema"})


def test_ref_never_has_siblings(document: dict[str, Any]) -> None:
    """В draft-07 `$ref` вытесняет соседние слова; описание рядом с ним было бы обманом."""
    nodes: list[dict[str, Any]] = []
    _collect_objects(document, nodes)

    assert [node for node in nodes if "$ref" in node and len(node) > 1] == []


def _collect_objects(node: object, found: list[dict[str, Any]]) -> None:
    if isinstance(node, dict):
        found.append(node)
        for value in node.values():
            _collect_objects(value, found)
    elif isinstance(node, list):
        for item in node:
            _collect_objects(item, found)


# --- читаемость контракта ---------------------------------------------------------


def test_every_field_is_described(document: dict[str, Any]) -> None:
    """Схему читает автор советника (этап 4), а не только тот, кто писал модели."""
    undescribed = [
        f"{owner}.{name}"
        for owner, schema in _objects_with_properties(document)
        for name, field in schema["properties"].items()
        if "description" not in field
    ]

    assert undescribed == []


def _objects_with_properties(document: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    definitions: dict[str, Any] = document["definitions"]
    return [("#", document), *((name, schema) for name, schema in definitions.items())]


# --- шаблон времени: единственное место, где схема и модель написаны дважды --------


@pytest.mark.parametrize(
    "value",
    [
        "2026-09-02T14:03:11",
        "2026-09-02T14:03:11.1",
        "2026-09-02T14:03:11.123456",
        "2026-09-02T14:03:11Z",
        "2026-09-02T14:03:11+03:00",
        "2026-09-02 14:03:11",
        "2026-09-02T14:03",
        "2026-09-02",
        "",
        "вчера",
    ],
)
def test_published_pattern_agrees_with_the_model(document: dict[str, Any], value: str) -> None:
    """Отправитель, проверивший тело по файлу, не должен получить отказ от сервера.

    Шаблон в схеме и разбор в pydantic — единственная пара, где одно и то же правило
    записано дважды (`WithJsonSchema`), поэтому их согласие проверяется, а не постулируется.
    """
    pattern = document["definitions"]["IngestDeal"]["properties"]["time_server"]["pattern"]
    accepted_by_schema = re.match(pattern, value) is not None

    try:
        server_time.validate_python(value)
        accepted_by_model = True
    except ValidationError:
        accepted_by_model = False

    assert accepted_by_schema == accepted_by_model


def test_pattern_cannot_express_the_calendar(document: dict[str, Any]) -> None:
    """Известный и неустранимый зазор: форма верна, даты не существует.

    Регулярным выражением календарь не проверить, поэтому «2026-13-45» файл пропускает,
    а сервер отвергает. Зазор записан тестом, чтобы он был решением, а не сюрпризом.
    """
    pattern = document["definitions"]["IngestDeal"]["properties"]["time_server"]["pattern"]

    assert re.match(pattern, "2026-13-45T14:03:11") is not None
    with pytest.raises(ValidationError):
        server_time.validate_python("2026-13-45T14:03:11")
