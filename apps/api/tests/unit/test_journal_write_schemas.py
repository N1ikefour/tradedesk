"""Тела записи журнала — S2-02.

Два правила этого файла стоят дороже остальных, потому что ошибка в любом из них выглядит
для человека не как ошибка, а как враньё интерфейса.

* **Обязательность полей.** `PUT` заменяет запись целиком (SPEC.md 5.4). Поле, у которого
  появился default, выпадает из `required`, и частичное тело автосохранения (`S2-07`)
  начинает молча стирать заметку с ответом `200`. Здесь это ловится по телу запроса,
  в `test_journal_contract.py` — по объявленной схеме.
* **Что считается заполненным.** От `is_filled` зависит `filled_at`, от него — фильтр
  `has_reflection` (S2-01) и иконка в таблице. Ошибка читается как «я же заполнил, а он
  говорит, что нет».
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from app.domains.journal.schemas import (
    MAX_NOTES_LENGTH,
    MAX_TAG_LENGTH,
    MAX_TAGS,
    JournalEntryUpdate,
    ReflectionUpdate,
    TagCreateRequest,
    fold_tag,
)

FULL_ENTRY: dict[str, Any] = {
    "notes": "разбор",
    "tags": ["trend"],
    "planned_entry": "1.08",
    "planned_sl": "1.07",
    "planned_tp": "1.10",
    "risk_amount": "50.00",
}

EMPTY_REFLECTION: dict[str, Any] = {
    "setup_grade": None,
    "execution_grade": None,
    "followed_plan": None,
    "emotion_before": None,
    "emotion_during": None,
    "emotion_after": None,
    "mistakes": [],
    "confidence": None,
    "free_text": None,
}


def entry(**overrides: Any) -> JournalEntryUpdate:
    return JournalEntryUpdate.model_validate({**FULL_ENTRY, **overrides})


def reflection(**overrides: Any) -> ReflectionUpdate:
    return ReflectionUpdate.model_validate({**EMPTY_REFLECTION, **overrides})


def field_errors(error: ValidationError) -> set[str]:
    return {".".join(str(part) for part in item["loc"]) for item in error.errors()}


# --- полная замена: пропущенное поле это ошибка, а не «оставь как было» --------


@pytest.mark.parametrize("missing", sorted(FULL_ENTRY))
def test_entry_rejects_a_partial_body(missing: str) -> None:
    """Тело без поля — 400 с его именем, а не тихое обнуление этого поля в базе."""
    body = {key: value for key, value in FULL_ENTRY.items() if key != missing}

    with pytest.raises(ValidationError) as error:
        JournalEntryUpdate.model_validate(body)

    assert missing in field_errors(error.value)


@pytest.mark.parametrize("missing", sorted(EMPTY_REFLECTION))
def test_reflection_rejects_a_partial_body(missing: str) -> None:
    body = {key: value for key, value in EMPTY_REFLECTION.items() if key != missing}

    with pytest.raises(ValidationError) as error:
        ReflectionUpdate.model_validate(body)

    assert missing in field_errors(error.value)


def test_entry_rejects_an_unknown_field() -> None:
    """Опечатка в имени поля не должна выглядеть как успешное сохранение."""
    with pytest.raises(ValidationError):
        JournalEntryUpdate.model_validate({**FULL_ENTRY, "note": "опечатка"})


def test_explicit_null_clears_a_field() -> None:
    """Явный `null` — законный способ очистить: он отличим от «не прислал»."""
    cleared = entry(notes=None, risk_amount=None, planned_entry=None)

    assert cleared.notes is None
    assert cleared.risk_amount is None
    assert cleared.planned_entry is None


# --- что считается заполненным (filled_at) ------------------------------------


def test_empty_reflection_is_not_filled() -> None:
    assert reflection().is_filled is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("setup_grade", "A"),
        ("execution_grade", "D"),
        ("followed_plan", True),
        ("emotion_before", "calm"),
        ("emotion_during", "fomo"),
        ("emotion_after", "tired"),
        ("mistakes", ["no_plan"]),
        ("confidence", 1),
        ("free_text", "поспешил"),
    ],
)
def test_any_single_answer_makes_the_reflection_filled(field: str, value: Any) -> None:
    """Одного ответа достаточно — SPEC.md 5.4: «хотя бы одно заполненное поле»."""
    assert reflection(**{field: value}).is_filled is True


def test_followed_plan_false_is_an_answer_not_an_absence() -> None:
    """«Плану не следовал» — самый содержательный ответ в журнале, а не пустое поле.

    Считать `false` незаполненным значило бы гасить иконку рефлексии ровно на тех
    сделках, ради разбора которых журнал и ведут.
    """
    assert reflection(followed_plan=False).is_filled is True


@pytest.mark.parametrize("blank", ["", "   ", "\n\t "])
def test_whitespace_free_text_is_not_an_answer(blank: str) -> None:
    """Строка из пробелов приводится к `null` и заполненной рефлексию не делает."""
    filled_in = reflection(free_text=blank)

    assert filled_in.free_text is None
    assert filled_in.is_filled is False


def test_empty_mistakes_is_not_an_answer() -> None:
    """Пустой массив — «ошибок не отмечено», то же самое, что не трогать поле."""
    assert reflection(mistakes=[]).is_filled is False


def test_confidence_lowest_value_is_an_answer() -> None:
    """У `confidence` нет нуля (1..5), поэтому минимум — это выбор, а не пустота."""
    assert reflection(confidence=1).is_filled is True


# --- рефлексия: словари и границы ---------------------------------------------


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("emotion_before", "счастлив"),
        ("emotion_during", "calm "),
        ("setup_grade", "E"),
        ("execution_grade", "a"),
    ],
)
def test_values_outside_the_vocabulary_are_rejected(field: str, value: str) -> None:
    """Ключ вне словаря сохранился бы, но подписи у него на фронте нет (SPEC.md 3.5)."""
    with pytest.raises(ValidationError):
        reflection(**{field: value})


def test_unknown_mistake_is_rejected() -> None:
    with pytest.raises(ValidationError):
        reflection(mistakes=["no_plan", "проспал"])


def test_repeated_mistakes_collapse_keeping_order() -> None:
    """Два одинаковых чипа — один чип; 400 здесь был бы придиркой."""
    assert reflection(mistakes=["revenge", "no_plan", "revenge"]).mistakes == [
        "revenge",
        "no_plan",
    ]


@pytest.mark.parametrize("value", [0, 6, -1])
def test_confidence_outside_one_to_five_is_rejected(value: int) -> None:
    with pytest.raises(ValidationError):
        reflection(confidence=value)


@pytest.mark.parametrize("value", [True, False])
def test_confidence_does_not_accept_a_boolean(value: bool) -> None:
    """`true` — не «уверенность 1»: bool наследует int, и pydantic пропустил бы его."""
    with pytest.raises(ValidationError):
        reflection(confidence=value)


# --- заметка ------------------------------------------------------------------


def test_notes_are_trimmed_and_blank_becomes_null() -> None:
    assert entry(notes="  разбор  ").notes == "разбор"
    assert entry(notes="   ").notes is None


def test_notes_keep_line_breaks() -> None:
    """Заметка многострочная: переводы строк здесь — содержание, а не мусор."""
    assert entry(notes="первая\nвторая").notes == "первая\nвторая"


def test_notes_reject_the_nul_byte() -> None:
    """Postgres не хранит `\\x00` в `text`: без проверки это была бы 500 на вставке."""
    with pytest.raises(ValidationError):
        entry(notes="раз\x00два")


def test_notes_longer_than_the_limit_are_rejected() -> None:
    with pytest.raises(ValidationError):
        entry(notes="я" * (MAX_NOTES_LENGTH + 1))


# --- числа плана --------------------------------------------------------------


def test_planned_prices_accept_a_string_without_going_through_float() -> None:
    """Строка — способ прислать точное значение; в ответ оно уходит тоже строкой."""
    assert entry(planned_entry="1.08543").planned_entry == Decimal("1.08543")


def test_risk_amount_must_be_positive() -> None:
    """SPEC.md 3.4: от него считается R. Ноль — деление на ноль в метриках (S2-05)."""
    with pytest.raises(ValidationError):
        entry(risk_amount="0")
    with pytest.raises(ValidationError):
        entry(risk_amount="-10")


def test_values_beyond_the_column_are_rejected_at_the_boundary() -> None:
    """Иначе `numeric(18,8)` отвергнет их уже в Postgres, то есть пятисоткой."""
    with pytest.raises(ValidationError):
        entry(planned_entry="10000000000")
    with pytest.raises(ValidationError):
        entry(risk_amount="10000000000000000")


# --- теги ---------------------------------------------------------------------


def test_tags_are_trimmed_and_keep_their_case() -> None:
    """DoD S2-02: trim, регистр сохраняется."""
    assert entry(tags=["  Trend  ", "Breakout"]).tags == ["Trend", "Breakout"]


def test_tags_repeated_in_another_case_collapse_to_the_first_spelling() -> None:
    """`Trend` и `trend` — один тег. Побеждает первое написание в самом списке."""
    assert entry(tags=["Trend", "trend", "TREND"]).tags == ["Trend"]


def test_tag_folding_is_case_insensitive_for_cyrillic_too() -> None:
    """Словарь тегов у человека русский тоже — `casefold`, а не `lower` по ASCII."""
    assert fold_tag("Пробой") == fold_tag("пробой")


@pytest.mark.parametrize("value", ["", "   "])
def test_empty_tag_is_rejected_not_dropped(value: str) -> None:
    """Молча выкинуть — значит сохранить не то, что прислали, и не сказать об этом."""
    with pytest.raises(ValidationError):
        entry(tags=[value])


def test_tag_with_a_comma_is_rejected() -> None:
    """По запятой разделяется `?tags=a,b`: такой тег нельзя было бы отфильтровать."""
    with pytest.raises(ValidationError):
        entry(tags=["trend,breakout"])


def test_tag_with_control_characters_is_rejected() -> None:
    with pytest.raises(ValidationError):
        entry(tags=["trend\nbreakout"])


def test_tag_longer_than_the_limit_is_rejected() -> None:
    with pytest.raises(ValidationError):
        entry(tags=["т" * (MAX_TAG_LENGTH + 1)])


def test_more_tags_than_allowed_is_rejected() -> None:
    with pytest.raises(ValidationError):
        entry(tags=[f"тег{index}" for index in range(MAX_TAGS + 1)])


def test_tag_limit_counts_unique_tags() -> None:
    """Повторы схлопнулись раньше подсчёта: 20 тегов, названных дважды, — это 20."""
    names = [f"тег{index}" for index in range(MAX_TAGS)]

    assert entry(tags=[*names, *names]).tags == names


# --- цвет тега ----------------------------------------------------------------


def test_tag_color_is_normalized_to_lowercase_hex() -> None:
    assert TagCreateRequest(name="trend", color="#2563EB").color == "#2563eb"


@pytest.mark.parametrize("value", ["red", "#25f", "2563eb", "#2563eb; content:x", "#2563ebff"])
def test_tag_color_outside_hex_is_rejected(value: str) -> None:
    """Цвет уезжает во фронт как значение стиля: произвольного текста там быть не должно."""
    with pytest.raises(ValidationError):
        TagCreateRequest(name="trend", color=value)


def test_tag_color_can_be_cleared_with_null() -> None:
    assert TagCreateRequest(name="trend", color=None).color is None


def test_tag_create_requires_the_color_field() -> None:
    """«Сохранил без цвета» и «не трогал цвет» обязаны выглядеть по-разному."""
    with pytest.raises(ValidationError):
        TagCreateRequest.model_validate({"name": "trend"})
