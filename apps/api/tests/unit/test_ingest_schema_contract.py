"""Соответствие `ingest-deals.schema.json` моделям и диалекту draft-07 (S1-01).

Тест не сравнивает два списка полей, написанных одной рукой: он пересобирает файл из
моделей и сверяет его с тем, что лежит в репозитории. Любое расхождение — лишнее поле
в схеме, забытая перегенерация, правка файла руками — делает его красным.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft7Validator
from jsonschema.exceptions import SchemaError
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
from app.domains.ingest.schemas import (
    MAX_BIGINT,
    IngestDeal,
    ServerTime,
    ServerUtcOffsetMinutes,
    batch_json_schema,
)

REGENERATE = "cd apps/api && python -m app.domains.ingest.schema_export"

# Сделка примера SPEC.md 5.3 как есть — та же, что в `test_ingest_schemas.py`. Нужна там,
# где сравниваются два читателя одного документа: модель и опубликованный файл.
_DEAL_EXAMPLE: dict[str, Any] = json.loads(
    (Path(__file__).resolve().parents[1] / "fixtures/ingest/spec-5.3-example.json").read_text(
        encoding="utf-8"
    )
)["deals"][0]

server_time = TypeAdapter(ServerTime)
offset_minutes = TypeAdapter(ServerUtcOffsetMinutes)


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


# --- метасхема draft-07 -----------------------------------------------------------

# Метасхема живёт в тесте, а не в `schema_export`: валидатор JSON Schema — dev-зависимость,
# в рантайм-образ он не едет, тела запросов сервер разбирает pydantic'ом.
#
# `pattern` метасхема объявляет строкой формата `regex`, но форматы проверяются только с
# явным чекером, и его состав зависит от того, что установлено рядом. Без `regex` проверка
# выродилась бы в пустую молча, поэтому его наличие проверяется отдельным тестом.
FORMATS = Draft7Validator.FORMAT_CHECKER

Mutation = Callable[[dict[str, Any]], None]


def _validate_against_metaschema(schema: dict[str, Any]) -> None:
    Draft7Validator.check_schema(schema, format_checker=FORMATS)


def _string_where_integer_is_required(schema: dict[str, Any]) -> None:
    schema["definitions"]["IngestDeal"]["properties"]["symbol"]["maxLength"] = "64"


def _required_as_a_bare_string(schema: dict[str, Any]) -> None:
    schema["required"] = "account_id"


def _type_outside_the_seven(schema: dict[str, Any]) -> None:
    schema["properties"]["account_id"]["type"] = "uuid"


def _pattern_that_is_not_a_regex(schema: dict[str, Any]) -> None:
    schema["definitions"]["IngestDeal"]["properties"]["symbol"]["pattern"] = "[A-Z"


def test_regex_format_checker_is_installed() -> None:
    assert "regex" in FORMATS.checkers


def test_committed_schema_validates_against_the_metaschema(document: dict[str, Any]) -> None:
    """Опубликованный файл разбирают чужие валидаторы, и споткнутся о него они.

    Тонко невалидная схема ломается не у нас: у автора советника MQL5 и у импорта CSV
    (`source: "ea" | "csv"`). Узнать об этом от них — худший из способов.
    """
    _validate_against_metaschema(document)


def test_build_schema_validates_against_the_metaschema() -> None:
    _validate_against_metaschema(build_schema())


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        pytest.param(_string_where_integer_is_required, "'64' is not of type 'integer'", id="type"),
        pytest.param(_required_as_a_bare_string, "is not of type 'array'", id="shape"),
        pytest.param(_type_outside_the_seven, "'uuid' is not valid under any", id="vocabulary"),
        pytest.param(_pattern_that_is_not_a_regex, "'[A-Z' is not a 'regex'", id="regex"),
    ],
)
def test_metaschema_catches_what_the_keyword_walk_cannot(mutate: Mutation, message: str) -> None:
    """Каждая мутация обязана пройти `check_draft_07` и упасть на метасхеме.

    Первая половина утверждения важнее второй и есть причина, по которой зависимость
    появилась: обход словаря смотрит только на имена ключевых слов и адреса ссылок,
    поэтому `"maxLength": "64"` для него неотличим от `"maxLength": 64`.
    """
    broken = build_schema()
    mutate(broken)

    check_draft_07(broken)

    with pytest.raises(SchemaError, match=re.escape(message)):
        _validate_against_metaschema(broken)


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
    Полный перечень таких мест — в `description` корня схемы.
    """
    pattern = document["definitions"]["IngestDeal"]["properties"]["time_server"]["pattern"]

    assert re.match(pattern, "2026-13-45T14:03:11") is not None
    with pytest.raises(ValidationError):
        server_time.validate_python("2026-13-45T14:03:11")


# --- правила, которые draft-07 выражает, а значит файл обязан их нести -------------


@pytest.mark.parametrize(
    "offset", [-855, -735, -721, -720, -180, 0, 1, 7, 45, 100, 180, 840, 841, 855]
)
def test_published_offset_agrees_with_the_model(document: dict[str, Any], offset: int) -> None:
    """Кратность 15 обязана быть видна отправителю вне Python, а не только серверу.

    `source: "ea" | "csv"` — это чужие отправители: советник на MQL5 сверяется с файлом,
    и правило, которого в файле нет, приходит к нему как необъяснимый 400.
    """
    published = Draft7Validator(document["properties"]["server_utc_offset_minutes"])

    try:
        offset_minutes.validate_python(offset)
        accepted_by_model = True
    except ValidationError:
        accepted_by_model = False

    assert published.is_valid(offset) == accepted_by_model


def test_published_offset_rejects_a_value_off_the_quarter_hour(document: dict[str, Any]) -> None:
    """Якорь для теста согласия: без него обе стороны могли бы разрешить 7 разом."""
    published = Draft7Validator(document["properties"]["server_utc_offset_minutes"])

    assert published.is_valid(180)
    assert not published.is_valid(7)


@pytest.mark.parametrize(
    ("deal_type", "symbol"),
    [
        (0, ""),
        (1, ""),
        (2, ""),
        (3, ""),
        (99, ""),
        (0, "EURUSD"),
        (2, "EURUSD"),
    ],
)
def test_published_symbol_rule_agrees_with_the_model(
    document: dict[str, Any], deal_type: int, symbol: str
) -> None:
    """Послабление X-44 условное, и условие draft-07 выразить умеет — значит обязан нести.

    Второе место после кратности смещения, где правило записано дважды: `if/then` в
    `json_schema_extra` и валидатор `_trading_deal_carries_a_symbol`. Разойдись они — и
    автор советника MQL5 получил бы 400 за тело, которое файл контракта разрешает.
    """
    published = Draft7Validator(document["definitions"]["IngestDeal"])
    body = dict(_DEAL_EXAMPLE, type=deal_type, symbol=symbol)

    try:
        IngestDeal.model_validate(body)
        accepted_by_model = True
    except ValidationError:
        accepted_by_model = False

    assert published.is_valid(body) == accepted_by_model


def test_published_symbol_rule_is_not_vacuous(document: dict[str, Any]) -> None:
    """Якорь для теста согласия: без него обе стороны могли бы разрешить всё разом."""
    published = Draft7Validator(document["definitions"]["IngestDeal"])

    assert published.is_valid(dict(_DEAL_EXAMPLE, type=2, symbol=""))
    assert not published.is_valid(dict(_DEAL_EXAMPLE, type=0, symbol=""))


@pytest.mark.parametrize(
    ("definition", "field"),
    [
        ("IngestDeal", "ticket"),
        ("IngestDeal", "order"),
        ("IngestDeal", "position_id"),
        ("IngestDeal", "magic"),
        ("IngestOpenPosition", "position_id"),
    ],
)
def test_published_integers_stop_at_the_bigint_column(
    document: dict[str, Any], definition: str, field: str
) -> None:
    """Верхняя граница целых выражается в draft-07, значит зазору здесь взяться неоткуда.

    Модель отвергает `2**63` (см. `test_ingest_schemas.py`), и ровно то же самое должен
    отвергать читатель файла — иначе он узнает о границе колонки из пятисотки.
    """
    published = document["definitions"][definition]["properties"][field]

    assert published["maximum"] == MAX_BIGINT
    assert not Draft7Validator(published).is_valid(MAX_BIGINT + 1)
