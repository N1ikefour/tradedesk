"""Чистота модуля, доказанная по его исходнику. Механизм — из S1-02.

Утверждение «функции чистые» стоит ровно столько, сколько ловит проверка: прошлая версия
этого кода в `test_normalizer.py` ловила ноль из трёх известных обходов и при этом
выглядела строгой. Поэтому механизм живёт в одном месте на весь проект, а не копией в
каждом тесте: дыру, найденную в одном модуле, чинить придётся один раз.

Что здесь **не** живёт — сам контракт. Белые списки импортов и builtins у каждого модуля
свои и остаются рядом с его тестом: они и есть та часть, которую читает ревьюер.

Разбирается **весь исходник модуля** по AST, а не его функции по одной. Обход через
`inspect.getmembers(..., isfunction)` не видел ни кода уровня модуля, ни методов классов:
`_BUILD_HOUR = datetime.now().hour` рядом с константами и метод на dataclass проходили
мимо него незамеченными. Дерево исходника покрывает и то, и другое, и заодно
comprehension'ы с лямбдами.
"""

from __future__ import annotations

import ast
import inspect
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

# Имена и атрибуты, обращение к которым означает выход из чистоты: часы машины, окружение,
# зона ОС, ввод-вывод. Нужны отдельно от белого списка builtins, потому что `datetime`
# импортировать можно, а `datetime.now()` вызывать нельзя — атрибуты белым списком не
# покрыть, не перечисляя заодно все поля предметной области. `astimezone` и `fromtimestamp`
# здесь потому, что на наивном времени они молча спрашивают зону процесса.
IMPURE_NAMES = frozenset(
    {
        "astimezone",
        "commit",
        "environ",
        "execute",
        "fromtimestamp",
        "getenv",
        "localtime",
        "monotonic",
        "now",
        "open",
        "perf_counter",
        "random",
        "time",
        "today",
        "utcnow",
    }
)

# Их нет в `IMPURE_NAMES` — сами по себе они ничего не делают, — но именно через них белый
# список обходится: имя собирается в рантайме и мимо любого списка проходит.
DYNAMIC_ENTRY_POINTS = frozenset(
    {"getattr", "eval", "exec", "__import__", "globals", "locals", "vars", "compile", "input"}
)

# Три обхода, каждый из которых прошлая версия проверки пропускала. Держатся здесь как
# образцы для теста проверки: механизм, который их не ловит, бесполезен.
IMPURE_SNIPPETS = {
    "module_level": "from datetime import datetime\n_BUILD_HOUR = datetime.now().hour\n",
    "class_method": (
        "from datetime import UTC, datetime\n"
        "class NormalizedDeal:\n"
        "    def stamped_at(self) -> datetime:\n"
        "        return datetime.now(UTC)\n"
    ),
    "name_assembled_at_runtime": (
        "from datetime import datetime\n"
        "def to_utc(value: datetime) -> datetime:\n"
        '    if getattr(datetime, "no" + "w")().year > 2030:\n'
        "        return value\n"
        "    return value\n"
    ),
}


@dataclass(frozen=True, slots=True)
class PurityContract:
    """Что модулю разрешено брать снаружи. Всё, чего здесь нет, — красный тест."""

    allowed_imports: frozenset[str]
    # Единственные builtins, которыми модулю разрешено пользоваться. Список белый, и в этом
    # суть: блоклист по именам обходится сборкой имени в рантайме — `getattr(datetime,
    # "no" + "w")()` не содержит слова `now` нигде, поэтому мимо блоклиста проходит. Слово
    # `getattr` в исходнике при этом есть, и белому списку его достаточно.
    allowed_builtins: frozenset[str]

    @property
    def guarded(self) -> frozenset[str]:
        """Имена, затенение которых снимает охрану, — модуль не вправе связывать ни одно.

        `bound_names` не различает области видимости, поэтому любое связывание имени в
        модуле вычёркивает его из `external_names` целиком. Параметр `open` (цена открытия —
        имя в этом домене естественное) снял бы охрану с `open(...)` во всём файле, и ни
        один тест бы не заметил.
        """
        return self.allowed_builtins | IMPURE_NAMES | DYNAMIC_ENTRY_POINTS


def module_tree(module: ModuleType) -> ast.Module:
    source = Path(inspect.getsourcefile(module) or "").read_text(encoding="utf-8")
    return ast.parse(source)


def imported_modules(tree: ast.AST) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def bound_names(tree: ast.AST) -> set[str]:
    """Всё, что модуль связывает сам: импорты, определения, аргументы, локальные имена."""
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Load):
            bound.add(node.id)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, ast.alias):
            bound.add((node.asname or node.name).split(".")[0])
        else:
            # `def`, `class`, `except ... as`, `type`-параметры: у всех имя лежит в `.name`,
            # и все они вводят имя в область видимости. Перечислять их поимённо не нужно —
            # достаточно того, что оно вводится.
            defined = getattr(node, "name", None)
            if isinstance(defined, str):
                bound.add(defined)
    return bound


def external_names(tree: ast.AST) -> set[str]:
    """Имена, взятые снаружи: не импортированы и не определены здесь — значит builtins."""
    used = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    return used - bound_names(tree)


def attribute_names(tree: ast.AST) -> set[str]:
    return {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}


def leaks(tree: ast.AST, contract: PurityContract) -> set[str]:
    """Чем модуль вышел за контракт: чужое имя либо обращение к часам, окружению, вводу-выводу."""
    outside = external_names(tree)
    reached = outside | attribute_names(tree)
    return (outside - contract.allowed_builtins) | (reached & IMPURE_NAMES)
