"""Сверка счёта: чей счёт открыт в терминале и наш ли он — `X-66`.

Это самый дорогой инвариант коллектора после идемпотентности. Библиотека `MetaTrader5`
подключается к тому терминалу, который найдёт, и не сообщает, что счёт там чужой. Ошибка
здесь не падает и не видна: сделки чужого счёта просто оказываются в чужом журнале, а
`deals` — append-only факты.
"""

from __future__ import annotations

import pytest

from collector import identity

OURS = identity.Watched(account_id="acc-1", login=293272, server="EGlobalTrade-Demo")
THEIRS = identity.Watched(account_id="acc-2", login=999111, server="Other-Broker-Demo")


def test_the_open_account_is_matched_by_login_and_server() -> None:
    match = identity.match_open_account(
        identity.OpenAccount(login=293272, server="EGlobalTrade-Demo"), [THEIRS, OURS]
    )
    assert match.status == "match"
    assert match.account_id == "acc-1"


def test_a_login_from_another_broker_is_not_our_account() -> None:
    """Номера демо-счетов у разных брокеров пересекаются, и это не теория.

    Совпадение только по логину означало бы, что история чужого демо-счёта уедет в наш
    журнал молча — и вынуть её оттуда будет нечем.
    """
    match = identity.match_open_account(
        identity.OpenAccount(login=293272, server="Other-Broker-Demo"), [OURS]
    )
    assert match.status == "server_mismatch"
    assert match.account_id == "acc-1"
    assert match.expected_server == "EGlobalTrade-Demo"


def test_an_unknown_login_is_refused_outright() -> None:
    match = identity.match_open_account(
        identity.OpenAccount(login=555000, server="EGlobalTrade-Demo"), [OURS, THEIRS]
    )
    assert match.status == "unknown_account"
    assert match.account_id is None


def test_no_accounts_at_all_is_refused_the_same_way() -> None:
    match = identity.match_open_account(
        identity.OpenAccount(login=293272, server="EGlobalTrade-Demo"), []
    )
    assert match.status == "unknown_account"


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("EGlobalTrade-Demo", "eglobaltrade-demo"),
        ("EGlobalTrade-Demo", "  EGlobalTrade-Demo  "),
        ("EGLOBALTRADE-DEMO", "EGlobalTrade-Demo"),
    ],
)
def test_server_names_are_compared_without_case_and_stray_spaces(left: str, right: str) -> None:
    """Человек списывает имя сервера глазами из терминала в карточку счёта."""
    assert identity.same_server(left, right)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("EGlobalTrade-Demo", "EGlobalTrade-Real"),
        ("EGlobalTrade-Demo", "EGlobalTradeDemo"),
        ("EGlobalTrade-Demo", ""),
    ],
)
def test_different_servers_stay_different(left: str, right: str) -> None:
    """Дефисы и пробелы внутри имени не выбрасываются: «Demo» и «Real» — разные серверы,
    и решать за человека, что он имел в виду, нельзя."""
    assert not identity.same_server(left, right)


def test_a_full_match_wins_over_a_login_only_match() -> None:
    """Порядок списка не должен решать: полное совпадение ищется первым проходом."""
    twin = identity.Watched(account_id="acc-3", login=293272, server="Other-Broker-Demo")
    match = identity.match_open_account(
        identity.OpenAccount(login=293272, server="EGlobalTrade-Demo"), [twin, OURS]
    )
    assert match.status == "match"
    assert match.account_id == "acc-1"


def test_two_accounts_matching_one_open_account_refuse_both() -> None:
    """Выбирать наугад нельзя: выбор делал бы порядок ответа assignments.

    Уникальность в БД сравнивает имя сервера посимвольно, а здесь оно сравнивается без
    регистра, — значит два таких счёта заводятся без всякой экзотики.
    """
    twin = identity.Watched(account_id="acc-2", login=293272, server="eglobaltrade-demo")
    match = identity.match_open_account(
        identity.OpenAccount(login=293272, server="EGlobalTrade-Demo"), [OURS, twin]
    )
    assert match.status == "ambiguous"
    assert match.account_id is None


def test_two_login_only_matches_refuse_both_too() -> None:
    """Тот же довод: назвать один из двух счётом-виновником — назвать наугад."""
    first = identity.Watched(account_id="acc-1", login=293272, server="Broker-A")
    second = identity.Watched(account_id="acc-2", login=293272, server="Broker-B")
    match = identity.match_open_account(
        identity.OpenAccount(login=293272, server="Broker-C"), [first, second]
    )
    assert match.status == "ambiguous"


def test_the_answer_does_not_depend_on_the_order_of_the_list() -> None:
    """Прямая проверка того, что раньше решал порядок: оба порядка дают один ответ."""
    twin = identity.Watched(account_id="acc-2", login=293272, server="eglobaltrade-demo")
    open_account = identity.OpenAccount(login=293272, server="EGlobalTrade-Demo")
    forward = identity.match_open_account(open_account, [OURS, twin])
    backward = identity.match_open_account(open_account, [twin, OURS])
    assert forward == backward


@pytest.mark.parametrize("login", ["293272", None, True, 29.32])
def test_a_login_that_is_not_a_whole_number_is_not_read(login: object) -> None:
    """Библиотека обещает целое, и обещание непроверяемое: терминала на macOS нет.

    `True` в списке не для красоты: в Python `bool` наследует `int`, и логин `True`
    молча стал бы счётом номер один.
    """

    class _Info:
        def __init__(self, value: object) -> None:
            self.login = value
            self.server = "EGlobalTrade-Demo"

    assert identity.read_open_account(_Info(login)) is None  # type: ignore[arg-type]


def test_a_whole_login_is_read_with_its_server() -> None:
    class _Info:
        login = 293272
        server = "EGlobalTrade-Demo"

    assert identity.read_open_account(_Info()) == identity.OpenAccount(
        login=293272, server="EGlobalTrade-Demo"
    )


def test_the_same_account_before_and_after_is_the_same_account() -> None:
    before = identity.OpenAccount(login=293272, server="EGlobalTrade-Demo")
    after = identity.OpenAccount(login=293272, server="eglobaltrade-demo")
    assert identity.stayed_the_same(before, after)


@pytest.mark.parametrize(
    "after",
    [
        identity.OpenAccount(login=999111, server="EGlobalTrade-Demo"),
        identity.OpenAccount(login=293272, server="EGlobalTrade-Real"),
    ],
)
def test_a_switched_account_is_noticed(after: identity.OpenAccount) -> None:
    """Человек вправе переключить счёт между чтением истории и отправкой батча."""
    before = identity.OpenAccount(login=293272, server="EGlobalTrade-Demo")
    assert not identity.stayed_the_same(before, after)
