"""Выгрузка сделок из запущенного терминала MetaTrader 5.

Запускать на Windows, где стоит терминал. Пароль не нужен: скрипт
подключается к УЖЕ ЗАПУЩЕННОМУ терминалу и только читает.

Что делает:
  1. забирает историю сделок за указанный период;
  2. обезличивает — номер счёта заменяется, имя владельца не пишется;
  3. складывает всё в JSON рядом со скриптом;
  4. печатает сводку, которая отвечает на наши открытые вопросы.

Установка (один раз, в командной строке Windows):
    pip install MetaTrader5

Запуск:
    python export_mt5_deals.py
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

try:
    import MetaTrader5 as mt5
except ImportError:
    raise SystemExit("Нет библиотеки. Выполните: pip install MetaTrader5")

# ── настройки ────────────────────────────────────────────────────────────────

DAYS_BACK = 365  # за какой период выгружать
KEEP_COMMENTS = True  # комментарии брокера. См. предупреждение в конце
OUT = Path(__file__).with_name("mt5-export.json")

# ─────────────────────────────────────────────────────────────────────────────


def fail(step: str) -> None:
    code, text = mt5.last_error()
    raise SystemExit(f"{step}: терминал ответил [{code}] {text}")


def main() -> None:
    if not mt5.initialize():
        fail("Подключение к терминалу")

    info = mt5.account_info()
    if info is None:
        mt5.shutdown()
        fail("Чтение данных счёта")

    now = datetime.now(UTC)
    deals = mt5.history_deals_get(now - timedelta(days=DAYS_BACK), now)
    if deals is None:
        mt5.shutdown()
        fail("Чтение истории сделок")

    rows = [d._asdict() for d in deals]
    for r in rows:
        if not KEEP_COMMENTS:
            r["comment"] = ""

    # смещение сервера брокера относительно UTC — нужно нам для времени сделок
    offset_minutes = None
    symbols = sorted({r["symbol"] for r in rows if r["symbol"]})
    for name in symbols:
        tick = mt5.symbol_info_tick(name)
        if tick and tick.time:
            delta = (tick.time - now.timestamp()) / 60
            offset_minutes = round(delta / 15) * 15
            break

    terminal = mt5.terminal_info()
    payload = {
        "exported_at": now.isoformat(),
        "account": {
            "login": 9999999,  # обезличено
            "currency": info.currency,
            "margin_mode": int(info.margin_mode),
            "trade_mode": int(info.trade_mode),
            "company": info.company,
            "server": info.server,
            "balance": info.balance,
            "equity": info.equity,
        },
        "server_utc_offset_minutes": offset_minutes,
        "terminal_build": getattr(terminal, "build", None),
        "deals_count": len(rows),
        "deals": rows,
    }
    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    mt5.shutdown()
    report(rows, info, offset_minutes, symbols)


def report(rows: list[dict], info, offset_minutes, symbols: list[str]) -> None:
    def places(value) -> int:
        d = Decimal(str(value)).normalize()
        return max(0, -d.as_tuple().exponent)

    print("\n" + "=" * 62)
    print(f"Готово: {len(rows)} сделок → {OUT.name}")
    print("=" * 62)

    print(f"\nВалюта счёта: {info.currency}")
    print(
        f"Режим позиций (margin_mode): {int(info.margin_mode)}  [0=netting, 1=exchange, 2=hedging]"
    )
    print(f"Смещение сервера от UTC: {offset_minutes} мин")

    types: dict[int, int] = {}
    for r in rows:
        types[r["type"]] = types.get(r["type"], 0) + 1
    print("\nТипы сделок (type → сколько):")
    for code in sorted(types):
        print(f"   {code:>3} → {types[code]}")

    print("\nentry у НЕторговых сделок (type >= 2) — наш вопрос №9:")
    non_trade = {}
    for r in rows:
        if r["type"] >= 2:
            non_trade[r["entry"]] = non_trade.get(r["entry"], 0) + 1
    print(f"   {non_trade or 'таких сделок нет'}")

    print("\nСделки типа «прочее» (type >= 4) с непустым position_id — вопрос №3:")
    other_with_pos = [r for r in rows if r["type"] >= 4 and r["position_id"]]
    print(f"   {len(other_with_pos)} шт.")
    if other_with_pos:
        s = other_with_pos[0]
        print(
            f"   пример: type={s['type']} position_id={s['position_id']} profit={s['profit']}"
        )

    print("\nОтменённые сделки (type 13/14) с position_id — вопрос №1, самый опасный:")
    cancelled = [r for r in rows if r["type"] in (13, 14) and r["position_id"]]
    print(
        f"   {len(cancelled)} шт."
        + (f", пример profit={cancelled[0]['profit']}" if cancelled else "")
    )

    print("\nЗнаков после запятой — вопрос №19 (от него зависит, сойдётся ли сверка):")
    for field in ("commission", "swap", "profit", "fee"):
        vals = {places(r[field]) for r in rows if r.get(field)}
        print(f"   {field:<11} → {sorted(vals) or [0]}")

    print(f"\nСимволы ({len(symbols)}) — вопросы №11–18 про суффиксы:")
    for name in symbols[:40]:
        print(f"   {name}")
    if len(symbols) > 40:
        print(f"   … и ещё {len(symbols) - 40}")

    if KEEP_COMMENTS:
        comments = sorted({r["comment"] for r in rows if r["comment"]})
        print(f"\n⚠️  В файле сохранены комментарии брокера ({len(comments)} разных).")
        print("   Просмотрите список ниже. Если там есть что-то личное —")
        print("   поставьте KEEP_COMMENTS = False вверху скрипта и запустите заново.")
        for c in comments[:25]:
            print(f"   {c!r}")
        if len(comments) > 25:
            print(f"   … и ещё {len(comments) - 25}")

    print(
        "\nНомер счёта в файле заменён на 9999999. Пароли не читаются и не сохраняются."
    )
    print("=" * 62 + "\n")


if __name__ == "__main__":
    main()
