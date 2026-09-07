# BOARD — доска задач

Updated: 2026-09-06

Статусы и переходы — `docs/WORKFLOW.md` §2. Формулировки задач и Definition of Done — **`SPEC.md` §12**, здесь не дублируются. Файл тикета `docs/tickets/<ID>.md` заводится в момент взятия задачи в работу.

Статус меняется одновременно здесь и в шапке файла тикета, в том же коммите, что и работа.

Колонка «Роль» — предполагаемый владелец; окончательный назначается при взятии в работу.

---

## Этап 0 — Фундамент

| ID | Задача | Роль | Статус | Ветка / PR |
|---|---|---|---|---|
| S0-01 | Скелет монорепо | infra | **Done** | [PR #1](https://github.com/N1ikefour/tradedesk/pull/1) |
| S0-02 | API-скелет | backend | **Done** | [PR #2](https://github.com/N1ikefour/tradedesk/pull/2) |
| S0-03 | Миграция ядра | backend | **Done** | [PR #3](https://github.com/N1ikefour/tradedesk/pull/3) |
| S0-04 | Auth | backend | **Done** | [PR #5](https://github.com/N1ikefour/tradedesk/pull/5) |
| S0-05 | Шифрование credentials | backend | **Done** | [PR #6](https://github.com/N1ikefour/tradedesk/pull/6) |
| S0-06 | Docker Compose local/prod | infra | **Done** | [PR #7](https://github.com/N1ikefour/tradedesk/pull/7) |
| S0-07 | Web-скелет | frontend | **Done** | [PR #9](https://github.com/N1ikefour/tradedesk/pull/9) |
| S0-08 | Settings | backend + frontend | **Done** | [PR #10](https://github.com/N1ikefour/tradedesk/pull/10) |
| S0-09 | SETUP.md черновик | infra | **Done** | [PR #12](https://github.com/N1ikefour/tradedesk/pull/12) |

## Этап 1 — Коллектор MT5 и ингест

| ID | Задача | Роль | Статус | Ветка / PR |
|---|---|---|---|---|
| S1-01 | JSON Schema ингеста | backend | **Done** | [PR #13](https://github.com/N1ikefour/tradedesk/pull/13) |
| S1-02 | Нормализатор deals | backend | **Done** | [PR #15](https://github.com/N1ikefour/tradedesk/pull/15) |
| S1-03 | Сборщик позиций (+ `X-44`) | backend | **Done** | [PR #26](https://github.com/N1ikefour/tradedesk/pull/26) |
| S1-04 | `POST /ingest/deals` | backend | In Progress | `feat/S1-04-ingest-deals` |
| S1-05 | `POST /ingest/heartbeat` + assignments | backend | **Done** | [PR #16](https://github.com/N1ikefour/tradedesk/pull/16) |
| S1-06 | Accounts API | backend | **Done** | [PR #14](https://github.com/N1ikefour/tradedesk/pull/14) |
| S1-07 | Символы | backend | **Done** | [PR #17](https://github.com/N1ikefour/tradedesk/pull/17) |
| S1-08 | Коллектор: mt5_client + worker | collector | Backlog | — |
| S1-09 | Коллектор: менеджер процессов, heartbeat | collector | Backlog | — |
| S1-10 | Коллектор: установка | collector | Backlog | — |
| S1-11 | UI Accounts | frontend | **Done** | [PR #18](https://github.com/N1ikefour/tradedesk/pull/18) |
| S1-12 | Сверка | backend | Backlog | — |

## Этап 2 — Журнал

| ID | Задача | Роль | Статус | Ветка / PR |
|---|---|---|---|---|
| S2-01 | Journal API: список и карточка | backend | **Done** | [PR #20](https://github.com/N1ikefour/tradedesk/pull/20) |
| S2-02 | Journal API: entry, reflection, tags, vocab | backend | **Done** | [PR #21](https://github.com/N1ikefour/tradedesk/pull/21) |
| S2-03 | Ручные сделки | backend | Backlog | — |
| S2-04 | Вложения | backend | Backlog | — |
| S2-05 | Календарь API + `analytics/summary` | backend | **Done** | [PR #23](https://github.com/N1ikefour/tradedesk/pull/23) |
| S2-06 | UI Journal таблица | frontend | **Done** | [PR #22](https://github.com/N1ikefour/tradedesk/pull/22) |
| S2-07 | UI Position card | frontend | **Done** | [PR #24](https://github.com/N1ikefour/tradedesk/pull/24) |
| S2-08 | UI Скриншоты | frontend | Backlog | — |
| S2-09 | UI Calendar | frontend | Backlog | — |
| S2-10 | UI Dashboard v1 | frontend | **Done** | [PR #27](https://github.com/N1ikefour/tradedesk/pull/27) |
| S2-11 | Переключатель счетов: создание и полировка | frontend | Backlog | перенесён из S1-11 |

## Веха «Первый тест»

| ID | Задача | Роль | Статус | Ветка / PR |
|---|---|---|---|---|
| T-01 | SETUP.md финальный | infra | Backlog | — |
| T-02 | Скрипты update/backup/restore | infra | In Progress | `feat/T-02-update-backup-restore` |
| T-03 | Экспорт/импорт данных пользователя | backend | Backlog | — |
| T-04 | Кнопка «Сообщить о проблеме» | frontend + backend | Backlog | — |
| T-05 | Чек-лист приёмки | оркестратор | Backlog | — |
| T-06 | Тест инструкции на чистой машине | принципал | Backlog | — |

---

## Что стоит между нами и передачей другу

Список открытых `X-NN` длинный, и это **не список дел перед передачей**. Это находки: каждый раз, когда ревью или проверка натыкались на что-то за пределами текущей задачи, оно записывалось сюда вместо того, чтобы раздуть чужой PR или потеряться. Большинство не нужно ни другу, ни вообще.

Реально на пути к «друг установил и пользуется» стоит вот это, и только это:

| | Что | Состояние |
|---|---|---|
| Ингест | ~~`S1-03`~~, `S1-04` | сборщик позиций готов на настоящих данных; остался эндпоинт приёма |
| Коллектор | `S1-08`, `S1-09`, `S1-10` | писать можно хоть сейчас; проверить — только на Windows с терминалом |
| Доставка | ~~`X-19`~~ → `T-02` → `T-01` | зип с релиза **готов и проверен живым прогоном**; дальше скрипты обновления и инструкция |
| Установка | `X-17` | на Windows нет `init.bat`: первый же шаг требует Git Bash |
| Windows-пути | `X-43` | у друга имя пользователя кириллицей — все пути по умолчанию не-ASCII |
| Первый вход | `X-16` | уход за кодом на страницу писем сбрасывает форму входа |
| Телефон | `X-36` | переключатель счетов ужал меню до одного пункта |

Всё остальное из списка ниже — либо наша гигиена (тесты, типы, CI, сеялка данных), либо укрепление против того, чего у нас пока нет (нагрузка, несколько пользователей, реальные данные брокера). Отдельно: `X-07` (Sentry получает исключение мимо скраба логов) опасен **только если задан `SENTRY_DSN`**; по умолчанию он пуст, и у друга Sentry не включится.

---

## Задачи вне SPEC

Баги, находки ревью, follow-up. ID `X-NN`, полное описание — в своём файле по `DEVELOPER_MANUAL.md` §8.3.

| ID | Задача | Роль | Статус | Ветка / PR |
|---|---|---|---|---|
| X-01 | `make ci-target`: гейт на целевой версии Python | infra | **Done** | [PR #7](https://github.com/N1ikefour/tradedesk/pull/7) |
| X-02 | Скраб секретов в логах: рекурсия по значениям и пароли БД | backend | **Done** | [PR #4](https://github.com/N1ikefour/tradedesk/pull/4) |
| X-03 | Формат ошибок в OpenAPI | backend | **Done** | [PR #8](https://github.com/N1ikefour/tradedesk/pull/8) |
| X-04 | Не-str ключи в логах роняют рендерер | backend | Todo | — |
| X-05 | Счётчик непросмотренного в логах врёт | backend | Todo | — |
| X-06 | Лимит по IP за прокси общий на всех | infra + backend | **Done** (частично, ограничение в итоге S0-06) | [PR #7](https://github.com/N1ikefour/tradedesk/pull/7) |
| X-07 | Sentry получает исключение мимо защиты логов | backend | Todo | — |
| X-08 | Вторая ротация до окончания первой уничтожает данные | backend | Todo | — |
| X-09 | Приложение собирается на импорте `app.main` | backend | Todo | — |
| X-10 | Инлайн-объявления ошибок растят типы впятеро | backend | Todo | — |
| X-11 | Заголовки ответов не объявлены в OpenAPI | backend | Todo | — |
| X-12 | Том postgres переживает worktree, `make up` умирает на пароле | infra | Todo | — |
| X-13 | Приостановленный запрос выглядит как вечная загрузка | frontend | Todo | — |
| X-14 | Новая зависимость не доезжает до существующего окружения | infra | Todo | — |
| X-15 | Линтер ловит кнопку без `type` | frontend | **Done** | [PR #11](https://github.com/N1ikefour/tradedesk/pull/11) |
| X-16 | Уход на страницу писем сбрасывает форму входа | frontend | Todo | — |
| X-17 | На Windows нет `init.bat` | infra | Todo | — |
| X-18 | Имя джоба в CI скрывает тесты web | infra | Todo | — |
| X-19 | Релизный zip-артефакт | infra | **Done** | [PR #25](https://github.com/N1ikefour/tradedesk/pull/25) |
| X-20 | Кэш `get_settings` отравляет соседние модули тестов | backend | Todo | — |
| X-21 | Свободный текст коллектора может вынести пароль наружу | backend + collector | Todo | — |
| X-22 | Комиссии с тремя знаками ломают сверку | backend | Todo | — |
| X-23 | Сервер молча переинтерпретирует то, что файл отвергает | backend | Todo | — |
| X-24 | Объявления ошибок сверяются не на всех статусах | backend | Todo | — |
| X-25 | Нет worker'а: `check_collectors` никто не зовёт | infra | **Done** | [PR #19](https://github.com/N1ikefour/tradedesk/pull/19) |
| X-26 | Счёт не освобождается от умершего коллектора | backend | Отложен | решение принципала, см. тикет |
| X-27 | Нет лимита попыток на маршрутах коллектора | backend | Todo | — |
| X-28 | Правки документов в `main` идут мимо гейта | infra | Todo | — |
| X-29 | Изменение словаря символов не доезжает до строк | backend | Todo | — |
| X-30 | Фокус-ловушка модала течёт на один Tab | frontend | Todo | — |
| X-31 | Worker жив, а работать не может | infra + backend | Todo | — |
| X-32 | Тело ошибки не сверяется с объявленной формой | backend | Todo | — |
| X-33 | Повторённый query-параметр теряет данные | backend | Todo | — |
| X-34 | Длину символа не ограничивает никто | backend | Todo | — |
| X-35 | Уникальность тегов без учёта регистра держится кодом | backend | Todo | — |
| X-36 | Переключатель ужал меню на телефоне до одного пункта | frontend | Todo | — |
| X-37 | Нечем засеять позиции: UI проверяется на пустом экране | backend | Todo | — |
| X-38 | NUL в query-параметре роняет журнал в 500 | backend | Todo | — |
| X-39 | Виртуализация журнала держится на константе высоты | frontend | Todo | — |
| X-40 | Границу торгового дня считают двое, общих примеров нет | frontend | Todo | — |
| X-41 | Схема разрешает закрытую позицию без времени закрытия | backend | Todo | — |
| X-42 | Экран без сети показывает вечную «Загрузка…» | frontend | Todo | — |
| X-43 | Кириллица в имени пользователя Windows | collector + infra | Todo | — |
| X-44 | Депозит не проходит контракт ингеста: пустой `symbol` | backend | **Done** | [PR #26](https://github.com/N1ikefour/tradedesk/pull/26) |
| X-45 | Индексы приходят с префиксом `$$` | backend | Todo | — |
| X-46 | Открытая позиция показывает причину своего закрытия | frontend | Todo | — |
| X-47 | Опубликованная схема и модель расходятся на переводе строки | backend | Todo | — |
| X-48 | Неточная формулировка инварианта уехала в OpenAPI | backend | Todo | — |
| X-49 | Изменённая сделка игнорируется бесследно | backend | Todo | — |
| X-50 | Два пересчёта `daily_stats` дерутся за первичный ключ | backend | Todo | — |
| X-51 | Потолок на размер тела стоит на одном маршруте | backend | Todo | — |
| X-52 | Токен коллектора даёт запись в любой счёт установки | backend + collector | Todo | — |
