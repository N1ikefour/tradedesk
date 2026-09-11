"""Цитаты `SETUP.md` сверяются с текстами, которые печатает код, — X-69.

`SETUP.md` цитирует то, что человек увидит на экране: сообщения коллектора, строки
интерфейса, вывод скриптов установки. Совпадение обязано быть дословным: инструкцию
ищут поиском по тексту ошибки, и цитата, разошедшаяся с экраном на одно слово, не
находится вовсе. Сверку делали руками дважды. `T-01` при этом процитировал сообщение,
которого в коде **не было никогда**, и оно прожило до `T-08`.

**Признак цитаты.** Автор ставит его сам — строкой-комментарием HTML перед блоком:

    <!-- quote: apps/collector-mt5/collector/messages.py -->
    > MetaTrader 5 не открыт или не отвечает коллектору. Откройте терминал, войдите…

Комментарий невидим читателю и называет файл, откуда взят текст. Без него блок — проза,
и его никто не проверяет: `>` в `SETUP.md` носит и объяснения, и вывод команд, поэтому
сама по себе блок-цитата признаком быть не может. Полное правило — комментарием в конце
`SETUP.md`, там его найдёт следующий автор.

**Что с чем сверяется.** Блок-цитата и каждая строка размеченного блока кода — целиком,
с подстановками: `{login}`, `${relative}`, `%TD_HOME%`, `$(td_cmd up)` в исходнике
становятся «здесь что угодно», поэтому инструкция вправе показать пример значения. Абзац
проверяется по-другому: в нём сверяется каждая строка в «ёлочках», и сверяется как
фрагмент — инструкция часто цитирует первое предложение длинного сообщения.

**Две границы, которые подстановка не переходит.**

*Граница строки.* Значение печатается внутри строки, поэтому подстановка не пускается
дальше её конца. Без этого запрета `TradeDesk поднят (профиль $PROFILE).` проглатывал две
следующие строки вывода `make up` целиком, и адрес, по которому человек открывает
приложение, можно было переименовать незаметно.

*Отдельная строка источника.* Однословный фрагмент («Счета», «Изменить») — это подпись
интерфейса, а подпись живёт в `ru.ts` отдельной строкой, поэтому от неё требуется точное
равенство. Иначе переименование прикрывается любым сообщением, где то же слово стоит в
другой фразе: «Счета» находилось внутри «Счета не загрузились.».

**Чего тест не делает.** Он не требует, чтобы каждое сообщение кода было процитировано,
и не ходит по неразмеченным абзацам. Ложное срабатывание здесь дороже пропуска: тест,
который краснеет от переноса строки в инструкции, снимут через неделю, и вместе с ним
уйдёт вся польза.
"""

from __future__ import annotations

import ast
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
SETUP_MD = REPO_ROOT / "SETUP.md"
SETUP_TEXT = SETUP_MD.read_text(encoding="utf-8") if SETUP_MD.is_file() else ""

MARKER = re.compile(r"^\s*<!--\s*quote:\s*(?P<sources>[^<>]+?)\s*-->\s*$")
MARKER_ANYWHERE = re.compile(r"<!--\s*quote:")
FENCE = re.compile(r"^\s*```")
GUILLEMETS = re.compile(r"«([^«»]+)»")

# Подстановка в шаблоне — любой диалект, потому что источники разные: `str.format` в
# питоне, `${}` в TypeScript, `%VAR%` в .bat, `$VAR` и `$(...)` в sh и PowerShell.
PLACEHOLDER = re.compile(
    r"""
      \$\( (?: [^()] | \( [^()]* \) )* \)   # $(...) — PowerShell, sh; одна вложенность
    | \$\{ [^{}]* \}                        # ${...} — TypeScript, sh
    | \{ [A-Za-z_]\w* \}                    # {name} — str.format
    | % [A-Za-z_][\w()]* %                  # %VAR% — .bat
    | \$ [A-Za-z_]\w*                       # $VAR — sh, PowerShell
    """,
    re.VERBOSE,
)

# Пунктуация вплотную к подстановке не сверяется: там, где код склеивает значение с
# текстом, инструкция пишет пример или многоточие и границу ставит по-своему. Слова
# сверяются дословно — и те, что до подстановки, и те, что после. Перевод строки в этой
# пунктуации разрешён только там, где его ставит сам код: иначе `Пользователь: $me`
# дотягивался через конец строки и забирал соседнюю строку вывода себе в значение.
EDGE_INLINE = r"[^\w«»\n]*"
EDGE_ACROSS_LINES = r"[^\w«»]*"

# Подстановка — это значение, а не кусок текста произвольной длины. Ограничений два.
# Потолок в токенах: без него шаблон вроде `${server} · счёт ${login}` подходит к любой
# фразе со словом «счёт» и делает сверку декорацией — проверено, он совпадал с абзацем
# прозы на шестнадцать строк. И граница строки: значение печатается внутри строки, а
# подстановка, которой позволено перешагнуть перевод строки, съедает соседнюю строку
# вывода целиком вместе с правом её переименовать.
SUBSTITUTION = r"(?:\S+(?:[^\S\n]+\S+){0,4})"

ESCAPES = {"n": "\n", "t": "\t", "r": "\r"}


# --------------------------------------------------------------------------------------
# Извлечение текстов из исходников
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Dialect:
    """Как достать из файла строки, которые он печатает человеку."""

    quotes: str
    backslash_escape: str
    doubled_quote_escape: str
    line_comment: str | None
    block_comment: tuple[str, str] | None
    concatenation: bool


DIALECTS: dict[str, Dialect] = {
    ".ts": Dialect("'\"`", "'\"`", "", "//", ("/*", "*/"), True),
    ".ps1": Dialect("'\"", "", "'", "#", None, True),
    ".sh": Dialect("'\"", '"', "", "#", None, False),
}


def _python_strings(text: str) -> list[str]:
    """Литералы питона берутся разбором, а не регуляркой: склейку соседних строк и
    тройные кавычки `ast` уже развернул."""
    return [
        node.value
        for node in ast.walk(ast.parse(text))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def _scan_strings(text: str, dialect: Dialect) -> list[tuple[int, int, str]]:
    """Строковые литералы файла как (начало, конец, значение)."""
    found: list[tuple[int, int, str]] = []
    index, size = 0, len(text)
    while index < size:
        char = text[index]
        if dialect.line_comment and text.startswith(dialect.line_comment, index):
            newline = text.find("\n", index)
            index = size if newline < 0 else newline + 1
            continue
        if dialect.block_comment and text.startswith(dialect.block_comment[0], index):
            opener, closer = dialect.block_comment
            end = text.find(closer, index + len(opener))
            index = size if end < 0 else end + len(closer)
            continue
        if char not in dialect.quotes:
            index += 1
            continue
        start = index
        index += 1
        buffer: list[str] = []
        while index < size:
            current = text[index]
            if char in dialect.backslash_escape and current == "\\" and index + 1 < size:
                buffer.append(ESCAPES.get(text[index + 1], text[index + 1]))
                index += 2
                continue
            if current == char:
                if char in dialect.doubled_quote_escape and text[index + 1 : index + 2] == char:
                    buffer.append(char)
                    index += 2
                    continue
                index += 1
                break
            buffer.append(current)
            index += 1
        found.append((start, index, "".join(buffer)))
    return found


def _joined_strings(text: str, dialect: Dialect) -> list[str]:
    """Литералы файла, со склейкой соседних через `+`.

    Длинные строки интерфейса в `ru.ts` собраны из кусков по границе строки исходника:
    без склейки тест сверял бы обрывки и молча пропускал бы правку в любом из них.
    """
    values: list[str] = []
    parts: list[str] = []
    previous_end: int | None = None
    for start, end, value in _scan_strings(text, dialect):
        glued = (
            dialect.concatenation
            and previous_end is not None
            and re.fullmatch(r"\s*\+\s*", text[previous_end:start]) is not None
        )
        if glued:
            parts.append(value)
        else:
            if parts:
                values.append("".join(parts))
            parts = [value]
        previous_end = end
    if parts:
        values.append("".join(parts))
    return values


def _bat_echo_lines(text: str) -> list[str]:
    """В .bat печатаемый текст не в кавычках: это хвост строки `echo`."""
    lines: list[str] = []
    for raw in text.splitlines():
        found = re.match(r"(?i)^\s*echo(?:\.|\s+)(.*)$", raw.strip())
        if found:
            lines.append(found.group(1).strip())
    return lines


@cache
def source_texts(relative: str) -> tuple[str, ...]:
    """Тексты, которые файл печатает человеку.

    Путь — как он написан в маркере цитаты, от корня репозитория: его же тест и печатает,
    когда файла нет. Имени файла для этого не хватает — `messages.py` в репозитории не
    один, и по имени маркер не найти.

    Сообщение из нескольких строк отдаётся целиком, построчно и началами: в блок-цитате
    инструкция переложит его по ширине страницы, а в блоке вывода покажет теми строками,
    какими его напечатал экран, — и часто только первыми, оборвав длинный отказ.
    """
    path = REPO_ROOT / relative
    if not path.is_file():
        raise AssertionError(
            f"маркер цитаты в SETUP.md называет файл {relative}, которого нет — "
            "путь пишется от корня репозитория"
        )
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".py":
        found = _python_strings(text)
    elif path.suffix in {".bat", ".cmd"}:
        found = _bat_echo_lines(text)
    else:
        dialect = DIALECTS.get(path.suffix)
        if dialect is None:
            raise AssertionError(f"нечем разобрать {relative}: диалект {path.suffix} не описан")
        found = _joined_strings(text, dialect)
    return (*found, *(piece for item in found if "\n" in item for piece in _pieces(item)))


def _pieces(message: str) -> list[str]:
    lines = message.splitlines()
    return [*lines, *("\n".join(lines[:count]) for count in range(2, len(lines)))]


# --------------------------------------------------------------------------------------
# Сравнение
# --------------------------------------------------------------------------------------


def normalize(text: str) -> str:
    """Перенос строки в документе и в коде расставлен по-разному — сверяется только
    текст, а не то, как он разложен по строкам."""
    return " ".join(text.split())


def as_screen(text: str) -> str:
    """Текст, как он лёг на экран: пробелы внутри строки сжаты, границы строк сохранены.

    Границы нужны подстановке и пунктуации вокруг неё — дальше конца своей строки они не
    идут. Словам границы не мешают: между ними в шаблоне стоит «любой пробел», перевод
    строки включая, поэтому переложить абзац по ширине страницы можно свободно.
    """
    return "\n".join(normalize(line) for line in text.splitlines() if line.strip())


def literal_parts(template: str) -> list[str]:
    """Куски шаблона между подстановками — то, что обязано совпасть дословно.

    Строки шаблона при этом сохранены: по ним видно, переносит ли строку сам код, и
    только там подстановка вправе оказаться на своей строке."""
    return PLACEHOLDER.split(as_screen(template))


def _has_own_words(template: str) -> bool:
    """Шаблон из одних подстановок (`${a} — ${b}`) подошёл бы к любой цитате и сделал
    бы тест декорацией. Такой в сравнении не участвует."""
    return any(len(word) >= 3 for word in re.findall(r"\w+", "".join(literal_parts(template))))


def _verbatim(text: str) -> str:
    """Слова — дословно, пробел между ними — любой: переложить абзац по ширине страницы
    инструкция вправе, и перевод строки внутри фразы ничего не меняет."""
    return r"\s+".join(re.escape(word) for word in text.split())


def _edge(stripped: str) -> str:
    """Чем сверяется пунктуация между словом и подстановкой. Перевод строки в ней
    разрешён ровно тогда, когда его ставит сам код: `не понимает:` и путь под ним — одна
    строка вывода для человека и две для терминала, а `Пользователь: $me` — одна и та
    же, и дотянуться из неё до соседней строки значение не вправе."""
    return EDGE_ACROSS_LINES if "\n" in stripped else EDGE_INLINE


def _punctuation(text: str, at_end: bool) -> str:
    """Пунктуация на краю куска — та, что снимается перед сверкой слов."""
    edge = rf"{EDGE_ACROSS_LINES}$" if at_end else rf"^{EDGE_ACROSS_LINES}"
    found = re.search(edge, text)
    return found.group() if found else ""


def _pattern(template: str) -> str:
    parts = literal_parts(template)
    chunks: list[str] = []
    for position, part in enumerate(parts):
        first, last = position == 0, position == len(parts) - 1
        text = part
        opening = "" if first else _punctuation(text, at_end=False)
        text = text[len(opening) :]
        closing = "" if last else _punctuation(text, at_end=True)
        text = text[: len(text) - len(closing)]
        if not first:
            chunks.append(SUBSTITUTION)
            chunks.append(_edge(opening))
        chunks.append(_verbatim(text))
        if not last:
            chunks.append(_edge(closing))
    return "".join(chunks)


def _tail_trimmed(text: str) -> str:
    """Точка в конце не сверяется: инструкция обрывает цитату на границе предложения."""
    return text.rstrip(".")


def matches_whole(quote: str, template: str) -> bool:
    """Цитата — это весь текст шаблона, с подставленными значениями."""
    if not _has_own_words(template):
        return False
    pattern = _pattern(_tail_trimmed(as_screen(template)))
    return re.fullmatch(pattern, _tail_trimmed(as_screen(quote))) is not None


def _fragment(text: str) -> str:
    return normalize(text).rstrip(" .…")


def matches_fragment(quote: str, template: str) -> bool:
    """Цитата — кусок текста шаблона: инструкция цитирует первое предложение длинного
    сообщения или одну подпись с экрана. Подстановок фрагмент не пересекает, поэтому
    сверяется дословно, без послаблений.

    Однословный фрагмент требует точного равенства со строкой источника. Подпись
    интерфейса — это отдельная строка в `ru.ts`, и подстрочный поиск по ней ничего не
    доказывает: «Счета» находится внутри «Счета не загрузились.», а «Изменить» — внутри
    «Изменить адрес», и подпись можно переименовать, оставив гейт зелёным. Фраза из двух
    слов и длиннее ищется подстрокой: инструкция цитирует начало сообщения, иногда
    обрывая его посреди фразы («TradeDesk не отвечает»).

    «Ёлочки» внутри исходной строки при этом не считаются: подпись, которую одна строка
    интерфейса цитирует в другой («…счёт стоит в состоянии «Ожидает коллектор»»),
    определена не там. Иначе переименование подписи оставляло бы тест зелёным — её
    прежнее имя нашлось бы в пересказе.
    """
    fragment = _fragment(quote)
    if len(fragment) < 3:
        return False
    if _fragment(template) == fragment:
        return True
    if len(fragment.split()) < 2:
        return False
    # Фрагмент обязан кончаться там же, где кончается слово: иначе «Ожидает коллектор»
    # находится внутри «Ожидает коллектора», и подпись можно переименовать незаметно.
    edges = rf"(?<!\w){re.escape(fragment)}(?!\w)"
    return any(
        re.search(edges, GUILLEMETS.sub(" ", normalize(part))) is not None
        for part in literal_parts(template)
    )


# --------------------------------------------------------------------------------------
# Разбор SETUP.md
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Quote:
    """Один размеченный блок инструкции."""

    line: int
    kind: str
    texts: tuple[str, ...]
    sources: tuple[str, ...]

    @property
    def id(self) -> str:
        return f"SETUP.md:{self.line}"


def _block_after(lines: list[str], start: int) -> tuple[str, list[str], int]:
    """Блок, к которому относится маркер: его вид, строки и номер первой из них."""
    index = start
    while index < len(lines) and not lines[index].strip():
        index += 1
    begin = index
    if index < len(lines) and FENCE.match(lines[index]):
        index += 1
        while index < len(lines) and not FENCE.match(lines[index]):
            index += 1
        return "fence", lines[begin + 1 : index], begin + 1
    while index < len(lines) and lines[index].strip():
        index += 1
    block = lines[begin:index]
    if block and block[0].lstrip().startswith(">"):
        return "blockquote", block, begin
    return "paragraph", block, begin


def parse_quotes(markdown: str) -> tuple[list[Quote], list[str]]:
    """Размеченные блоки и жалобы на саму разметку.

    Жалоба возвращается, а не кидается: опечатка в маркере — правка документа, и гасить
    ею сбор всех тестов приложения нельзя. Разбор на импорте это и делал: одна битая
    строка в `SETUP.md` роняла сбор, и ни один тест api не запускался вовсе.
    """
    lines = markdown.splitlines()
    quotes: list[Quote] = []
    problems: list[str] = []
    for number, line in enumerate(lines, start=1):
        marker = MARKER.match(line)
        if marker is None:
            continue
        sources = tuple(part.strip() for part in marker.group("sources").split(",") if part.strip())
        kind, block, block_start = _block_after(lines, number)
        if not block:
            problems.append(f"SETUP.md:{number}: маркер цитаты ничего не размечает")
            continue
        if kind == "blockquote":
            text = " ".join(item.lstrip().lstrip(">").strip() for item in block)
            quotes.append(Quote(block_start + 1, kind, (text,), sources))
        elif kind == "fence":
            screen = tuple(normalize(item) for item in block if item.strip())
            quotes.append(Quote(block_start + 1, kind, screen, sources))
        else:
            paragraph = " ".join(block)
            fragments = GUILLEMETS.findall(paragraph.replace("**", "").replace("`", ""))
            if not fragments:
                problems.append(
                    f"SETUP.md:{number}: маркер стоит над абзацем без «ёлочек» — цитировать нечего"
                )
                continue
            quotes.append(Quote(block_start + 1, kind, tuple(fragments), sources))
    return quotes, problems


QUOTES, MARKUP_PROBLEMS = parse_quotes(SETUP_TEXT)
SOURCES = sorted({path for quote in QUOTES for path in quote.sources})

# Фактическая разметка на момент X-69 — 62 блока и 107 текстов в них. Числа записаны
# порогами снизу: новая цитата их перерастает и правки теста не требует, а потеря
# разметки роняет тест — против неё эта страховка и заведена. Число блоков вдобавок
# сверяется с числом маркеров в файле, так что разбор, который перестал видеть половину
# маркеров, порогом не прикроется.
MIN_MARKED_BLOCKS = 62
MIN_QUOTED_TEXTS = 107

# Фактический разброс на момент X-69 — от 77 строк (`run-collector.bat`) до 612
# (`ru.ts`). Порог вдвое ниже минимума: правка источника не должна требовать правки
# теста, а сломанный разбор отдаёт единицы строк или ноль.
MIN_SOURCE_TEXTS = 40


# --------------------------------------------------------------------------------------
# Тесты
# --------------------------------------------------------------------------------------


def _templates(quote: Quote) -> list[str]:
    return [template for path in quote.sources for template in source_texts(path)]


def _uncovered(texts: tuple[str, ...], templates: list[str]) -> str | None:
    """Первая строка блока вывода, которую не удалось отнести ни к одному сообщению.

    Одно сообщение занимает в блоке то одну строку, то несколько, и по виду блока не
    отличить сообщение из двух строк от двух отдельных. Поэтому блок разбирается
    перебором с возвратом: сначала самый длинный кусок, какой целиком совпадёт с
    сообщением, а если остаток после него не разобрался — кусок короче. Без возврата
    первая же удачная склейка забирала бы строки, которые нужны следующему сообщению.
    """
    stuck = 0
    hopeless: set[int] = set()

    def walk(start: int) -> bool:
        nonlocal stuck
        stuck = max(stuck, start)
        if start == len(texts):
            return True
        if start in hopeless:
            return False
        for end in range(len(texts), start, -1):
            block = "\n".join(texts[start:end])
            if any(matches_whole(block, template) for template in templates) and walk(end):
                return True
        hopeless.add(start)
        return False

    return None if walk(0) else texts[stuck]


def unmatched(quote: Quote) -> str | None:
    """Первый кусок блока, которого нет в исходниках, или `None`, если сошлось всё."""
    templates = _templates(quote)
    if quote.kind == "paragraph":
        return next(
            (
                text
                for text in quote.texts
                if not any(matches_fragment(text, template) for template in templates)
            ),
            None,
        )
    if quote.kind == "blockquote":
        text = quote.texts[0]
        return None if any(matches_whole(text, t) for t in templates) else text
    return _uncovered(quote.texts, templates)


@pytest.mark.parametrize("quote", QUOTES, ids=[quote.id for quote in QUOTES])
def test_quoted_text_is_what_the_code_prints(quote: Quote) -> None:
    missing = unmatched(quote)

    assert missing is None, (
        f"{quote.id}: этого текста нет в {', '.join(quote.sources)}.\n"
        f"  в инструкции: {normalize(missing or '')}\n"
        "  Либо текст в коде изменили, а инструкцию нет — тогда правьте инструкцию.\n"
        "  Либо это не экранный текст — тогда снимите маркер цитаты с блока."
    )


def test_markup_is_well_formed() -> None:
    """Опечатка в маркере — красный тест, а не погасшая сьюта: разбор её больше не кидает
    исключением на импорте."""
    assert not MARKUP_PROBLEMS, "\n".join(MARKUP_PROBLEMS)


def test_setup_is_actually_marked_up() -> None:
    """Страховка на саму страховку: опечатка в разборе дала бы ноль цитат и зелёный
    тест на любом расхождении."""
    markers = len(MARKER_ANYWHERE.findall(SETUP_TEXT))
    blocks = len(QUOTES)
    texts = sum(len(quote.texts) for quote in QUOTES)

    assert SETUP_MD.is_file(), f"{SETUP_MD} не на месте — сверять цитаты не с чем"
    assert blocks == markers, f"маркеров цитат в файле {markers}, а разбор увидел блоков {blocks}"
    assert blocks >= MIN_MARKED_BLOCKS, (
        f"размеченных блоков стало {blocks}, было {MIN_MARKED_BLOCKS}"
    )
    assert texts >= MIN_QUOTED_TEXTS, f"сверяемых текстов стало {texts}, было {MIN_QUOTED_TEXTS}"
    assert {quote.kind for quote in QUOTES} == {"blockquote", "fence", "paragraph"}
    assert "apps/collector-mt5/collector/messages.py" in SOURCES
    assert "apps/web/src/i18n/ru.ts" in SOURCES


@pytest.mark.parametrize("path", SOURCES)
def test_source_yields_its_texts(path: str) -> None:
    """Сломанный разбор источника оставил бы пустой список — и каждая цитата из него
    упала бы на ровном месте. Пусть падает одна понятная проверка."""
    texts = source_texts(path)
    assert len(texts) >= MIN_SOURCE_TEXTS, (
        f"{path}: разбор нашёл строк {len(texts)} — сломался разбор, а не цитаты"
    )
    assert any(len(text) >= 30 for text in texts), f"{path}: нашлись только обрывки"


# --------------------------------------------------------------------------------------
# Тесты на сам сличитель. Без них тест выглядит рабочим, даже если сравнивает пустоту.
# --------------------------------------------------------------------------------------

MESSAGE = (
    "MetaTrader 5 не открыт или не отвечает коллектору. Откройте терминал, войдите в счёт и "
    "оставьте окно открытым: коллектор синхронизирует тот счёт, который открыт."
)


def test_rewrapped_quote_still_matches() -> None:
    """Переносы строк в инструкции переставляют при любой правке абзаца."""
    rewrapped = MESSAGE.replace("Откройте", "\n   Откройте").replace("счёт и", "счёт\nи")

    assert matches_whole(rewrapped, MESSAGE)


def test_changed_word_is_caught() -> None:
    assert not matches_whole(MESSAGE.replace("не открыт", "закрыт"), MESSAGE)


def test_dropped_sentence_is_caught() -> None:
    assert not matches_whole(MESSAGE.split(". ")[0], MESSAGE)


def test_substituted_value_is_allowed_but_words_around_it_are_not() -> None:
    template = "Счёт не в USD: валюта счёта {currency}. TradeDesk v1 работает только с ним."

    assert matches_whole(
        "Счёт не в USD: валюта счёта EUR. TradeDesk v1 работает только с ним.", template
    )
    assert not matches_whole(
        "Счёт не в USD: валюта счёта EUR. TradeDesk v2 работает только с ним.", template
    )


def test_substitution_does_not_eat_the_next_line() -> None:
    """Дыра, найденная ревью X-69: подстановка в конце строки дотягивалась до соседних
    строк вывода, и они не сверялись ничем. Значение остаётся внутри своей строки."""
    template = "TradeDesk поднят (профиль $PROFILE)."
    block = "TradeDesk поднят (профиль local).\n  Приложение   http://localhost:5173"

    assert matches_whole("TradeDesk поднят (профиль local).", template)
    assert not matches_whole(block, template)


def test_value_on_its_own_line_is_still_a_substitution() -> None:
    """Обратная сторона того же запрета: вывод сам переносит значение на свою строку, и
    это не соседнее сообщение, а та же подстановка."""
    template = "В пути к папке установки есть символы, которые Docker не понимает:\n\n    $TD_ROOT"
    block = "В пути к папке установки есть символы, которые Docker не понимает:\n    C:\\tradedesk"

    assert matches_whole(block, template)


def test_single_word_caption_needs_its_own_string() -> None:
    """Однословная подпись сверяется только целиком: внутри чужого сообщения она
    находится и оставляет переименование незамеченным."""
    assert matches_fragment("Счета", "Счета")
    assert not matches_fragment("Счета", "Счета не загрузились.")
    assert matches_fragment("TradeDesk не отвечает", "TradeDesk не отвечает по адресу {api_url}")


def test_template_without_own_words_matches_nothing() -> None:
    """`${a} — ${b}` подошёл бы к любой строке и сделал бы гейт декорацией."""
    assert not matches_whole("что угодно — хоть что", "${label} — ${value}")


def test_invented_message_is_caught() -> None:
    """Регрессия `T-01`: инструкция цитировала «Счёт … не выдан этому коллектору» —
    строки, которой в коде нет и не было. Прожила до `T-08`."""
    invented = "Счёт 5001234 не выдан этому коллектору"
    messages = source_texts("apps/collector-mt5/collector/messages.py")

    assert not any(matches_whole(invented, text) for text in messages)
    assert not any(matches_fragment(invented, text) for text in messages)
    assert any("не выдал этому коллектору" in text for text in messages), (
        "похожее сообщение в коде всё-таки есть — иначе тест ловил бы отсутствие файла"
    )


def test_missing_source_names_the_path_from_the_marker() -> None:
    """`messages.py` в репозитории не один: в жалобе стоит путь, как он написан в
    маркере, иначе исчезнувший файл по ней не найти."""
    with pytest.raises(AssertionError, match=r"apps/collector-mt5/collector/no-such-file\.py"):
        source_texts("apps/collector-mt5/collector/no-such-file.py")


# --------------------------------------------------------------------------------------
# Тесты на сам гейт: подменяют источник в памяти и ждут красного. Без них «мутация
# ловится» держится на том, что кто-то намерит это руками ещё раз.
# --------------------------------------------------------------------------------------


def _instead_of_sources(
    monkeypatch: pytest.MonkeyPatch, replacement: Callable[[str], tuple[str, ...]]
) -> None:
    """Подменить чтение источников на время теста: сверка ходит за текстами через имя
    модуля, поэтому подменяется оно."""
    monkeypatch.setattr(sys.modules[__name__], "source_texts", replacement)


def _renaming(pristine: dict[str, tuple[str, ...]], word: str) -> Callable[[str], tuple[str, ...]]:
    """Источник, в котором слово переименовали, — правка кода без правки инструкции."""

    def texts(path: str) -> tuple[str, ...]:
        return tuple(text.replace(word, "ПОДМЕНА") for text in pristine[path])

    return texts


def test_every_block_needs_its_source(monkeypatch: pytest.MonkeyPatch) -> None:
    """Источник, из которого не вычитался ни один текст, обязан ронять все свои блоки —
    иначе сломанный разбор источника выглядел бы как сошедшаяся сверка."""
    _instead_of_sources(monkeypatch, lambda path: ())

    assert [quote.id for quote in QUOTES if unmatched(quote) is None] == []


@pytest.mark.parametrize("quote", QUOTES, ids=[quote.id for quote in QUOTES])
def test_renaming_in_the_source_breaks_the_block(
    quote: Quote, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Правка слова в коде без правки инструкции роняет гейт — то, за чем тест и заведён.

    Проверяется на каждом блоке и в памяти: слова цитаты по очереди переименовываются в
    текстах источника, и блок обязан покраснеть хотя бы на одном. Иначе блок помечен, но
    не закреплён ничем — ровно та дыра, которую ревью X-69 нашло руками в выводе
    `make up`: три строки из восьми подстановка съедала, и переименовать их можно было
    незаметно. Слова, которые в исходнике стоят под подстановкой (пример пути, номер
    счёта, имя сервера), закрепить нельзя по устройству сверки — поэтому «хотя бы на
    одном», а не «на каждом».
    """
    pristine = {path: source_texts(path) for path in quote.sources}
    words = {word for text in quote.texts for word in re.findall(r"\w{4,}", text)}

    for word in sorted(words, key=len, reverse=True):
        _instead_of_sources(monkeypatch, _renaming(pristine, word))
        if unmatched(quote) is not None:
            return

    pytest.fail(
        f"{quote.id}: ни одного слова блока переименование в {', '.join(quote.sources)} не "
        "ломает — значит, блок помечен, а сверять в нём нечего. Либо в блоке одни "
        "подстановки и маркер с него надо снять, либо сверка перестала работать."
    )


FOREIGN_LINE = "ПОДМЕНА строки-такой-нет"

OUTPUT_BLOCKS = [quote for quote in QUOTES if quote.kind == "fence"]


@pytest.mark.parametrize("quote", OUTPUT_BLOCKS, ids=[quote.id for quote in OUTPUT_BLOCKS])
def test_no_room_for_a_line_nobody_checks(quote: Quote) -> None:
    """В блоке вывода нет места, куда можно вписать строку и остаться незамеченным.

    Так и была устроена дыра, которую нашло ревью X-69: подстановка дотягивалась до
    соседних строк, и три строки из восьми в выводе `make up` не сверялись ничем — в том
    числе та, из которой человек берёт адрес приложения. Мерить это по одной строке руками
    и значило бы мерить заново после каждой правки, поэтому чужая строка подставляется во
    все места каждого блока: на прежней сверке таких мест было двенадцать в шести блоках
    из одиннадцати.
    """
    templates = _templates(quote)
    swallowed = [
        at
        for at in range(len(quote.texts) + 1)
        if _uncovered((*quote.texts[:at], FOREIGN_LINE, *quote.texts[at:]), templates) is None
    ]

    assert swallowed == [], (
        f"{quote.id}: чужую строку на местах {swallowed} сверка проглотила — значит, "
        "соседние строки блока можно переименовать незаметно"
    )
