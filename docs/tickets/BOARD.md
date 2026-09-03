# BOARD — доска задач

Updated: 2026-09-03

Статусы и переходы — `docs/WORKFLOW.md` §2. Формулировки задач и Definition of Done — **`SPEC.md` §12**, здесь не дублируются. Файл тикета `docs/tickets/<ID>.md` заводится в момент взятия задачи в работу.

Статус меняется одновременно здесь и в шапке файла тикета, в том же коммите, что и работа.

Колонка «Роль» — предполагаемый владелец; окончательный назначается при взятии в работу.

---

## Этап 0 — Фундамент

| ID | Задача | Роль | Статус | Ветка / PR |
|---|---|---|---|---|
| S0-01 | Скелет монорепо | infra | **Done** | [PR #1](https://github.com/N1ikefour/tradedesk/pull/1) |
| S0-02 | API-скелет | backend | **Done** | [PR #2](https://github.com/N1ikefour/tradedesk/pull/2) |
| S0-03 | Миграция ядра | backend | In Progress | `feat/S0-03-core-migration` |
| S0-04 | Auth | backend | Backlog | — |
| S0-05 | Шифрование credentials | backend | Backlog | — |
| S0-06 | Docker Compose local/prod | infra | Backlog | — |
| S0-07 | Web-скелет | frontend | Backlog | — |
| S0-08 | Settings | backend + frontend | Backlog | — |
| S0-09 | SETUP.md черновик | infra | Backlog | — |

## Этап 1 — Коллектор MT5 и ингест

| ID | Задача | Роль | Статус | Ветка / PR |
|---|---|---|---|---|
| S1-01 | JSON Schema ингеста | backend | Backlog | — |
| S1-02 | Нормализатор deals | backend | Backlog | — |
| S1-03 | Сборщик позиций | backend | Backlog | — |
| S1-04 | `POST /ingest/deals` | backend | Backlog | — |
| S1-05 | `POST /ingest/heartbeat` + assignments | backend | Backlog | — |
| S1-06 | Accounts API | backend | Backlog | — |
| S1-07 | Символы | backend | Backlog | — |
| S1-08 | Коллектор: mt5_client + worker | collector | Backlog | — |
| S1-09 | Коллектор: менеджер процессов, heartbeat | collector | Backlog | — |
| S1-10 | Коллектор: установка | collector | Backlog | — |
| S1-11 | UI Accounts | frontend | Backlog | — |
| S1-12 | Сверка | backend | Backlog | — |

## Этап 2 — Журнал

| ID | Задача | Роль | Статус | Ветка / PR |
|---|---|---|---|---|
| S2-01 | Journal API: список и карточка | backend | Backlog | — |
| S2-02 | Journal API: entry, reflection, tags, vocab | backend | Backlog | — |
| S2-03 | Ручные сделки | backend | Backlog | — |
| S2-04 | Вложения | backend | Backlog | — |
| S2-05 | Календарь API + `analytics/summary` | backend | Backlog | — |
| S2-06 | UI Journal таблица | frontend | Backlog | — |
| S2-07 | UI Position card | frontend | Backlog | — |
| S2-08 | UI Скриншоты | frontend | Backlog | — |
| S2-09 | UI Calendar | frontend | Backlog | — |
| S2-10 | UI Dashboard v1 | frontend | Backlog | — |
| S2-11 | Полировка переключателя счетов | frontend | Backlog | — |

## Веха «Первый тест»

| ID | Задача | Роль | Статус | Ветка / PR |
|---|---|---|---|---|
| T-01 | SETUP.md финальный | infra | Backlog | — |
| T-02 | Скрипты update/backup/restore | infra | Backlog | — |
| T-03 | Экспорт/импорт данных пользователя | backend | Backlog | — |
| T-04 | Кнопка «Сообщить о проблеме» | frontend + backend | Backlog | — |
| T-05 | Чек-лист приёмки | оркестратор | Backlog | — |
| T-06 | Тест инструкции на чистой машине | принципал | Backlog | — |

---

## Задачи вне SPEC

Баги, находки ревью, follow-up. ID `X-NN`, полное описание — в своём файле по `DEVELOPER_MANUAL.md` §8.3.

| ID | Задача | Роль | Статус | Ветка / PR |
|---|---|---|---|---|
| X-01 | `make ci-target`: гейт на целевой версии Python | infra | Todo | — |
| X-02 | Скраб секретов в логах: рекурсия по значениям и пароли БД | backend | Todo | — |
| X-03 | Формат ошибок в OpenAPI | backend | Todo | — |
