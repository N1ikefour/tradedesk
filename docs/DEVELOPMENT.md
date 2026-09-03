# DEVELOPMENT — локальная разработка

Updated: 2026-09-03

---

## Статус: окружение ещё не собрано

`Makefile`, `docker-compose.yml` и приложения создаются в задачах `S0-01` (скелет, линтеры, CI) и `S0-06` (Docker Compose, `make init`). До их мержа команд ниже **не существует** — это план, а не инструкция.

Пока проверки запускаются напрямую тем инструментом, который есть, и в итоге задачи явно указывается, что именно было запущено.

---

## Что понадобится на машине

| Инструмент | Зачем | Проверено на машине принципала (macOS, 2026-09-03) |
|---|---|---|
| Docker + Compose | вся локальная инфраструктура | да, Docker 29.6.1 |
| Git | — | да |
| Node ≥ 20 | `apps/web` | да, v22.23.1 |
| Python 3.12 | `apps/api` вне контейнера (опционально) | локально 3.14; в контейнере — 3.12 по `SPEC.md` §2.2 |
| `gh` | PR | да, авторизован |

Windows-машина с MetaTrader 5 нужна только для коллектора (`S1-08`+). На macOS и Linux `MetaTrader5` не работает — это не чинится, см. `CLAUDE.md` §9.

---

## Команды (появятся в S0-01/S0-06)

```
make init      # .env из .env.example с генерацией секретов
make up        # docker compose --profile local up -d
make down
make test      # pytest (api) + vitest (web)
make lint      # ruff + mypy + eslint + prettier --check
make migrate   # alembic upgrade head внутри контейнера api
make revision m="описание"
make types     # openapi → apps/web/src/api/schema.d.ts
```

---

## Переменные окружения

Шаблон — `.env.example` (содержимое зафиксировано в `SPEC.md` §11.2). Реальный `.env` генерирует `make init`; в репозиторий он не попадает.

Секреты вводит принципал сам. Ассистент проверяет только **присутствие** переменной (`present` / `MISSING`), никогда не печатает значение.

`MASTER_KEY` после первого backfill credentials не меняется и не теряется — иначе данные счетов нечитаемы.

---

## Тесты

- Backend — `pytest`, интеграционные через testcontainers (Postgres, minio).
- Frontend — `vitest` + Testing Library; smoke — Playwright.
- Тестовая БД защищена guard'ом: имя обязано содержать `_test`, guard падает до первого запроса.
- Порог покрытия `domains/ingest` и `domains/analytics` — 90 %.

---

## Entry points — с чего начать задачу типа Y

Заполняется по мере появления кода. Пока: любая задача начинается с `CLAUDE.md` §1 (read order) и своего пункта в `SPEC.md` §12.

---

## Troubleshooting

Пусто — проблем ещё не встречали. Наполняется реальными случаями, а не предположениями.
