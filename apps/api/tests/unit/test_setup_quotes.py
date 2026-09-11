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
сама по себе блок-цитата признаком быть не может. Полное правило — во врезке в начале
`SETUP.md`, там его найдёт следующий автор.

**Что с чем сверяется.** Блок-цитата и каждая строка размеченного блока кода — целиком,
с подстановками: `{login}`, `${relative}`, `%TD_HOME%`, `$(td_cmd up)` в исходнике
становятся «здесь что угодно», поэтому инструкция вправе показать пример значения. Абзац
проверяется по-другому: в нём сверяется каждая строка в «ёлочках», и сверяется как
фрагмент — инструкция часто цитирует первое предложение длинного сообщения.

**Чего тест не делает.** Он не требует, чтобы каждое сообщение кода было процитировано,
и не ходит по неразмеченным абзацам. Ложное срабатывание здесь дороже пропуска: тест,
который краснеет от переноса строки в инструкции, снимут через неделю, и вместе с ним
уйдёт вся польза.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
SETUP_MD = REPO_ROOT / "SETUP.md"

MARKER = re.compile(r"^\s*<!--\s*quote:\s*(?P<sources>[^<>]+?)\s*-->\s*$")
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
# сверяются дословно — и те, что до подстановки, и те, что после.
EDGE_PUNCTUATION = r"[^\w«»]*"

# Подстановка — это значение, а не кусок текста произвольной длины. Без потолка шаблон
# вроде `${server} · счёт ${login}` подходит к любой фразе со словом «счёт» и делает
# сверку декорацией: проверено — он совпадал с абзацем прозы на шестнадцать строк.
SUBSTITUTION = r"(?:\S+(?:\s\S+){0,4})"

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


def source_texts(path: Path) -> list[str]:
    """Тексты, которые файл печатает человеку.

    Сообщение из нескольких строк отдаётся целиком, построчно и началами: в блок-цитате
    инструкция переложит его по ширине страницы, а в блоке вывода покажет теми строками,
    какими его напечатал экран, — и часто только первыми, оборвав длинный отказ.
    """
    if not path.is_file():
        raise AssertionError(
            f"маркер цитаты в SETUP.md называет файл {path.name}, которого нет — "
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
            raise AssertionError(f"нечем разобрать {path.name}: диалект {path.suffix} не описан")
        found = _joined_strings(text, dialect)
    return [*found, *(piece for item in found if "\n" in item for piece in _pieces(item))]


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


def literal_parts(template: str) -> list[str]:
    """Куски шаблона между подстановками — то, что обязано совпасть дословно."""
    return PLACEHOLDER.split(normalize(template))


def _has_own_words(template: str) -> bool:
    """Шаблон из одних подстановок (`${a} — ${b}`) подошёл бы к любой цитате и сделал
    бы тест декорацией. Такой в сравнении не участвует."""
    return any(len(word) >= 3 for word in re.findall(r"\w+", "".join(literal_parts(template))))


def _pattern(template: str) -> str:
    parts = literal_parts(template)
    chunks: list[str] = []
    for position, part in enumerate(parts):
        first, last = position == 0, position == len(parts) - 1
        text = part
        if not first:
            text = re.sub(rf"^{EDGE_PUNCTUATION}", "", text)
        if not last:
            text = re.sub(rf"{EDGE_PUNCTUATION}$", "", text)
        if not first:
            chunks.append(f"{SUBSTITUTION}{EDGE_PUNCTUATION}")
        chunks.append(re.escape(text))
        if not last:
            chunks.append(EDGE_PUNCTUATION)
    return "".join(chunks)


def _tail_trimmed(text: str) -> str:
    """Точка в конце не сверяется: инструкция обрывает цитату на границе предложения."""
    return normalize(text).rstrip(".")


def matches_whole(quote: str, template: str) -> bool:
    """Цитата — это весь текст шаблона, с подставленными значениями."""
    if not _has_own_words(template):
        return False
    return re.fullmatch(_pattern(_tail_trimmed(template)), _tail_trimmed(quote)) is not None


def matches_fragment(quote: str, template: str) -> bool:
    """Цитата — кусок текста шаблона: инструкция цитирует первое предложение длинного
    сообщения или одну подпись с экрана. Подстановок фрагмент не пересекает, поэтому
    сверяется дословно, без послаблений.

    «Ёлочки» внутри исходной строки при этом не считаются: подпись, которую одна строка
    интерфейса цитирует в другой («…счёт стоит в состоянии «Ожидает коллектор»»),
    определена не там. Иначе переименование подписи оставляло бы тест зелёным — её
    прежнее имя нашлось бы в пересказе.
    """
    fragment = normalize(quote).rstrip(" .…")
    if len(fragment) < 3:
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


def parse_quotes(markdown: str) -> list[Quote]:
    lines = markdown.splitlines()
    quotes: list[Quote] = []
    for number, line in enumerate(lines, start=1):
        marker = MARKER.match(line)
        if marker is None:
            continue
        sources = tuple(part.strip() for part in marker.group("sources").split(",") if part.strip())
        kind, block, block_start = _block_after(lines, number)
        if not block:
            raise AssertionError(f"SETUP.md:{number}: маркер цитаты ничего не размечает")
        if kind == "blockquote":
            text = " ".join(item.lstrip().lstrip(">").strip() for item in block)
            quotes.append(Quote(block_start + 1, kind, (text,), sources))
        elif kind == "fence":
            quotes.append(
                Quote(block_start + 1, kind, tuple(i for i in block if i.strip()), sources)
            )
        else:
            paragraph = " ".join(block)
            fragments = GUILLEMETS.findall(paragraph.replace("**", "").replace("`", ""))
            if not fragments:
                raise AssertionError(
                    f"SETUP.md:{number}: маркер стоит над абзацем без «ёлочек» — цитировать нечего"
                )
            quotes.append(Quote(block_start + 1, kind, tuple(fragments), sources))
    return quotes


QUOTES = parse_quotes(SETUP_MD.read_text(encoding="utf-8"))
SOURCES = sorted({path for quote in QUOTES for path in quote.sources})
TEXTS: dict[str, list[str]] = {path: source_texts(REPO_ROOT / path) for path in SOURCES}


# --------------------------------------------------------------------------------------
# Тесты
# --------------------------------------------------------------------------------------


def _templates(quote: Quote) -> list[str]:
    return [template for path in quote.sources for template in TEXTS[path]]


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
    # Блок вывода. Одно сообщение занимает в нём то одну строку, то несколько, и по виду
    # блока не отличить сообщение из двух строк от двух отдельных. Поэтому блок режется
    # жадно: сначала пробуется самый длинный кусок, какой целиком совпадёт с сообщением.
    start = 0
    while start < len(quote.texts):
        for end in range(len(quote.texts), start, -1):
            joined = " ".join(quote.texts[start:end])
            if any(matches_whole(joined, template) for template in templates):
                start = end
                break
        else:
            return quote.texts[start]
    return None


@pytest.mark.parametrize("quote", QUOTES, ids=[quote.id for quote in QUOTES])
def test_quoted_text_is_what_the_code_prints(quote: Quote) -> None:
    missing = unmatched(quote)

    assert missing is None, (
        f"{quote.id}: этого текста нет в {', '.join(quote.sources)}.\n"
        f"  в инструкции: {normalize(missing or '')}\n"
        "  Либо текст в коде изменили, а инструкцию нет — тогда правьте инструкцию.\n"
        "  Либо это не экранный текст — тогда снимите маркер цитаты с блока."
    )


def test_setup_is_actually_marked_up() -> None:
    """Страховка на саму страховку: опечатка в разборе дала бы ноль цитат и зелёный
    тест на любом расхождении."""
    texts = sum(len(quote.texts) for quote in QUOTES)

    assert texts >= 60, "разметка цитат в SETUP.md пропала или разбор её не видит"
    assert {quote.kind for quote in QUOTES} == {"blockquote", "fence", "paragraph"}
    assert "apps/collector-mt5/collector/messages.py" in SOURCES
    assert "apps/web/src/i18n/ru.ts" in SOURCES


@pytest.mark.parametrize("path", SOURCES)
def test_source_yields_its_texts(path: str) -> None:
    """Сломанный разбор источника оставил бы пустой список — и каждая цитата из него
    упала бы на ровном месте. Пусть падает одна понятная проверка."""
    texts = TEXTS[path]
    assert len(texts) >= 5, f"{path}: разбор не нашёл строк — сломался разбор, а не цитаты"
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


def test_template_without_own_words_matches_nothing() -> None:
    """`${a} — ${b}` подошёл бы к любой строке и сделал бы гейт декорацией."""
    assert not matches_whole("что угодно — хоть что", "${label} — ${value}")


def test_invented_message_is_caught() -> None:
    """Регрессия `T-01`: инструкция цитировала «Счёт … не выдан этому коллектору» —
    строки, которой в коде нет и не было. Прожила до `T-08`."""
    invented = "Счёт 5001234 не выдан этому коллектору"
    messages = source_texts(REPO_ROOT / "apps/collector-mt5/collector/messages.py")

    assert not any(matches_whole(invented, text) for text in messages)
    assert not any(matches_fragment(invented, text) for text in messages)
    assert any("не выдал этому коллектору" in text for text in messages), (
        "похожее сообщение в коде всё-таки есть — иначе тест ловил бы отсутствие файла"
    )
