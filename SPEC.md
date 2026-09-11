# SPEC — техническая спецификация v1 (этапы 0–2 и веха «Первый тест»)

Версия 1.28 — 11 сентября 2026 (v1.1: guard тестовой БД в DoD S0‑02, оговорка про инструментальные зависимости в 2.3; v1.2: домен `mail` в 2.1; v1.3: формат блобов credentials и `key_version` как отпечаток ключа, ADR‑0003; v1.4: инфраструктурные переменные окружения в 11.2; v1.5: словарь кодов ошибок в 5.1 приведён к реальности, ADR‑0004; v1.5.1: уточнено, что 415 фреймворк не порождает; v1.6: `GET /users/timezones` в 5.7 и требование серверного списка зон; v1.7: дистрибуция zip-архивом с релиза вместо `git clone`, `update` в 11.3 переписан, ADR-0005; v1.8: исправлен `time_msc` в примере 5.3 — расходился с `time_server` на год, найдено сверкой в `S1-01`; v1.9: `jsonschema` в 2.3 как dev/test-зависимость — опубликованный `ingest-deals.schema.json` читают валидаторы вне Python, и проверять его метасхемой обходом словаря нельзя; v1.10: `sync_requested_at` добавлен в DDL 3.2 — его требовали 5.2, 5.6 и 8.2, а в схеме колонки не было; `broker` добавлен в изменяемые поля `PATCH /accounts/{id}` в 5.2; v1.11: assignments в 5.6 отдаёт конверт `{items}` вместо голого массива — массив некуда расширять, а курсорная пагинация 5.1 потребовала бы ломающей правки; v1.12: в 9.3 зафиксировано, что порог «коллектор не на связи» на фронте не дублируется — вердикт приходит с сервера, иначе четвёртая копия числа разошлась бы молча; v1.13: в 5.4 оговорено, что `result='be'` это точный ноль и потому почти всегда пуст, и что `attachments` в карточке приходит с `S2-04`; v1.14: в 5.4 записаны решения `S2-02`, которых спека не фиксировала, а код принял: оба `PUT` требуют все поля тела, `POST /journal/tags` — upsert, меняющий написание на всех позициях, `DELETE` тега снимает его со всех позиций, и обе эти операции двигают `updated_at` у затронутых записей журнала; v1.15: в 9.3 в перечень фильтров журнала добавлено состояние позиции — параметр `status` есть у эндпоинта 5.4 и на экране `S2-06`, а в перечне его не было; v1.16: в 5.5 и 5.4 к ответам `analytics/summary` и календаря добавлены `breakeven` и `fee`, а к дню календаря — границы `starts_at`/`ends_at` с зоной и часом начала дня: без первых двух на экране не сходятся `trades = wins+losses+breakeven` и `net_pnl = gross+commission+swap+fee`, без вторых `S2-09` пересчитывал бы границу дня второй раз. Там же записано, что сводка считает только закрытые позиции и потому расходится с колонкой журнала, когда в списке видны открытые; v1.17: в 5.1 добавлен `413 payload_too_large` — его требовал 5.3 п. 1, а в словаре кодов его не было, и объявить его в OpenAPI было нечем; v1.18: в 5.3 п. 6 и в таблице 10 `refresh_daily_stats` получает от ингеста **отрезок `time_utc`**, а не готовый список дней: день режется по зоне и границе дня владельца счёта, а ингест владельца не видит — решение принципала по итогам ревью `S1-04`, чтобы правило торгового дня осталось в одном месте; v1.19: в 5.3 убрано обещание, что сервисный токен ограничен закреплёнными счетами — проверить это нечем, батч не несёт `collector_id`; сказано прямо, что токен глобален для установки, и почему это не граница; v1.20: в 8.2 файл лога коллектора стал файлом на счёт (процесс на счёт, а общий `RotatingFileHandler` между процессами теряет записи), добавлен `LOG_DIR`; в 8 записано, что строка, заведомо отвергаемая границей, не отправляется — иначе она остановила бы счёт навсегда; по итогам ревью то же правило распространено на открытые позиции, а смещение часов брокера принимается только после подтверждения обновившейся котировкой; v1.21: в 8.2 записаны решения `S1-09`, которых спека не фиксировала — менеджер молчит о счёте, чей процесс объяснил свой уход сам (код 4), и цена этого в том, что его `state=running` значит «коллектор ведёт счёт», а не «процесс жив»; ряд пауз перезапуска назван исполняемым (5→10→20→40→80 с) и оговорено его квантование тиком менеджера; молчание assignments замораживает пул целиком, включая перезапуски; крах менеджера уходит на карточки счетов через `state=error`. В ограничениях 8.3 добавлено, что жёсткое завершение менеджера оставляет процессы счетов сиротами — `daemon=True` работает только через `atexit`); v1.22: в 8.2 п. 4 записана установка `S1-10` — версия Python названа явно (ровно 3.12, отказ на остальных), зависимости ставятся один раз, `COLLECTOR_TOKEN` переносится в `collector.env` из `.env` установки, остановка идёт файлом `stop-collector.bat` — сначала просьба менеджеру выйти самому, потом задача, менеджер и процессы счетов силой, и что из этого получилось, скрипт говорит словами, кодировка `.bat` и `.ps1` задана и закреплена тестом; в 8.1 добавлен `LOG_DIR`; в 8.3 — Планировщик заданий вместо службы Windows и его молчаливость; v1.23: в 9.3 у разбивки по счетам в календаре появилось требование эквивалента по нажатию там, где наведения нет, — по итогам `S2-09`: наведение было записано как способ, и на сенсорном планшете разбивка оказывалась недостижима глазами, оставаясь доступной только диктору; v1.24: в 9.2 записаны решения `S2-11` — пресет «Все реальные» показывается только при счетах обоих видов (без реальных он даёт пустую выборку, а у первого пользователя все счета демо), предупреждение о смешении считается по фактическому составу выборки а не по имени пресета, и заведение счёта из переключателя не закрывает окно молча: под ним нет списка счетов, который бы ответил, что произошло; v1.25: в 12 у `T‑01` скриншоты отложены до `T‑06` — снимать их надо на той машине, для которой написан текст, то есть на Windows, а Windows у нас нет; снимок с macOS, выданный за Windows, инструкцию не улучшает. Там же исправлено «Git, клонирование»: дистрибуция стала zip-архивом ещё в `v1.7`, а строка `T‑01` осталась от прежнего способа и требовала того, чего `SETUP.md` не делает и делать не должен; v1.26: в 8.2 убрано обещание, что мягкая остановка показывает «Коллектор остановлен» на карточках счетов — `apply_heartbeat` пишет `status_message` только при `state='error'`, и такого состояния нет в перечне 9.3. Записано, что карточки два исхода остановки **не различают** (в обоих через пять минут «коллектор не на связи»), а разница видна в окне скрипта и в диспетчере задач: менеджер гасит процессы счетов сам, `TerminateProcess` оставляет их сиротами. Та же ошибка исправлена в абзаце про крах менеджера. Найдено ревью `X-62`; ошибочное обоснование было моим, в `S1-10`; v1.27: по итогам первого прогона установки на живой Windows §8 переписан целиком — **терминал MetaTrader 5 открывает человек, коллектор подключается к открытому и синхронизирует тот счёт, в который человек вошёл** (`X-66`, решение `T-07`, ADR-0006). Копии терминала, вход по паролю, пул процессов, `MAX_ACCOUNTS`, `MT5_TERMINAL_EXE` и `MT5_PORTABLE_ROOT` отменены: `initialize(path=…, portable=True)` возвращал `IPC timeout` всегда, а `initialize()` без аргументов работал мгновенно. Добавлены `STATE_DIR`, сверка счёта по логину и серверу дважды за тик с отказом при расхождении и неоднозначности, `trust_env=False` (`X-68`) и код ошибки MT5 в логе (`X-67`). В 3.2, 5.2, 5.6, 9.2, 9.3 убран пароль торгового счёта: форма его не спрашивает, API не требует, assignments не отдаёт. В 11.3 `.bat` находят `bash` по известным путям, а не через `PATH` (`X-63`), и вывод скриптов называет команды своей платформы (`X-64`); v1.28: в 12 у `T-01` записан переписанный по итогам первого прогона `SETUP.md` (`T-08`) — глава про коллектор описывает открытый человеком терминал (ADR-0006), §1 получил измеренную последовательность включения WSL2 с указанием шагов, требующих сети (`X-65`); скриншотов по-прежнему нет). Дополняет `PLAN.md`. Написана для разработки с AI‑агентами: каждый раздел самодостаточен, решения зафиксированы, неопределённости вынесены в раздел 14.

Рабочее название продукта: **TradeDesk** (переименовать одной заменой — используется только в UI‑строках и `APP_NAME`).

---

## 0. Как пользоваться этим документом агентам

1. Перед любой задачей прочитать разделы 1–3 (правила, структура, модель данных) и раздел, к которому относится задача.
2. Ничего из зафиксированных решений не менять молча. Если решение мешает — предложить изменение в PR‑описании и в `docs/adr/`, не в коде.
3. Работать маленькими PR: одна задача из раздела 12 — один PR. В PR обязательно: что сделано, как проверить, какие тесты добавлены.
4. Тесты обязательны для: нормализатора deals, сборщика позиций, идемпотентности ингеста, расчёта метрик, auth‑потока. UI‑тесты — только smoke (страница открывается, основной сценарий проходит).
5. Не добавлять зависимости без явной причины в PR. Разрешённый набор — раздел 2.3.
6. Все строки UI — русский язык, файл `apps/web/src/i18n/ru.ts` (структура под будущий английский).
7. Секреты — только через переменные окружения. Ни одного секрета, пароля или токена в логах, тестовых фикстурах и коде.

---

## 1. Обзор системы

```
┌──────────────────────────┐        ┌──────────────────────────────────────┐
│ Windows (ноутбук / VPS)  │        │ Docker Compose (та же машина / VPS)   │
│                          │        │                                       │
│  MT5 terminal #1 ──┐     │        │  web (React SPA, nginx)  :5173/:80    │
│  MT5 terminal #2 ──┤     │  HTTP  │  api (FastAPI)           :8000        │
│                    ▼     │ ─────▶ │  worker (arq)                         │
│  collector-mt5 (Python)  │        │  postgres :5432   redis :6379         │
│  heartbeat + batches     │        │  minio (S3, только local‑профиль)     │
└──────────────────────────┘        └──────────────────────────────────────┘
                                                 ▲
                                        браузер пользователя
```

Компоненты:

- **api** — FastAPI, единственная точка записи в БД. Домены: `auth`, `accounts`, `ingest`, `journal`, `analytics`, `files`, `system`.
- **worker** — arq, фоновые задачи: пересчёт `daily_stats`, обработка загруженных файлов, отправка писем.
- **collector-mt5** — Python‑процесс на Windows вне Docker; по одному дочернему процессу на активный счёт; забирает deals из терминала и шлёт батчи в `POST /api/v1/ingest/deals`.
- **web** — Vite + React SPA; в проде отдаётся nginx‑контейнером, проксирующим `/api` в `api`.

---

## 2. Репозиторий и соглашения

### 2.1 Структура

```
trading/
  PLAN.md  SPEC.md  CLAUDE.md  SETUP.md  README.md
  .env.example
  docker-compose.yml            # профили: local, prod
  Makefile                      # make up / down / test / lint / migrate / types
  apps/
    api/
      pyproject.toml
      alembic/                  # миграции
      app/
        main.py                 # создание приложения, роутеры, middleware
        core/                   # config.py, db.py, security.py, logging.py, errors.py
        domains/
          auth/                 # router.py, service.py, schemas.py, models.py
          accounts/
          ingest/               # router.py, normalizer.py, position_builder.py, schemas.py
          journal/
          mail/                 # EmailProvider, dev_outbox (S0-04)
          analytics/            # metrics.py, daily_stats.py
          files/
          system/               # health, version
        workers/                # arq: tasks.py, settings.py
      tests/
        fixtures/               # реальные выгрузки deals (обезличенные)
        unit/  integration/
    web/
      package.json  vite.config.ts  tailwind.config.ts
      src/
        api/                    # сгенерированные типы + клиент (openapi-fetch)
        app/                    # роутер, layout, провайдеры
        features/               # auth, accounts, journal, calendar, dashboard, settings
        components/ui/          # shadcn
        i18n/ru.ts
        lib/                    # formatters (money, date, tz), account-switcher store
    collector-mt5/
      pyproject.toml
      collector/
        main.py                 # менеджер процессов
        worker.py               # один счёт: initialize → sync loop
        mt5_client.py           # обёртка над MetaTrader5
        api_client.py           # HTTP к api
        config.py
      collector.env.example
      run-collector.bat  install-service.ps1
  packages/
    shared-schemas/
      ingest-deals.schema.json  # контракт батча deals (JSON Schema draft‑07)
    mql5-ea/                    # этап 4, пока пусто
  infra/
    Caddyfile  nginx.conf  scripts/{start,stop,update,backup}.{bat,sh}
  docs/
    adr/  metrics.md  fixtures.md
```

### 2.2 Соглашения

- Python 3.12, `ruff` (line-length 100), `mypy --strict` для `domains/ingest` и `domains/analytics`, остальное `mypy` без strict. Async везде в API; синхронный код — только в коллекторе.
- TypeScript strict, `eslint` + `prettier`. Импорты по алиасу `@/`.
- Именование БД: snake_case, таблицы во множественном числе, PK `id` (UUID v7 для пользовательских сущностей, BIGINT для `deals`), время — `timestamptz`, всегда UTC. Деньги — `numeric(18,2)`, цены и объёмы — `numeric(18,8)`.
- API: префикс `/api/v1`, JSON, snake_case в полях, ошибки в формате раздела 5.1.
- Коммиты: Conventional Commits (`feat(ingest): …`, `fix(web): …`).
- Ветки: `main` (защищена, деплой), `feat/<task-id>-<slug>`.

### 2.3 Разрешённые зависимости

**api:** fastapi, uvicorn, sqlalchemy[asyncio] 2.x, asyncpg, alembic, pydantic v2, pydantic-settings, arq, redis, httpx, structlog, sentry-sdk, python-multipart, boto3 (S3), cryptography, pandas (только analytics), pytest, pytest-asyncio, factory-boy, testcontainers (интеграционные тесты с Postgres), jsonschema (только dev/test: валидация опубликованного `ingest-deals.schema.json` по метасхеме draft-07; в рантайм-образ не входит).

**web:** react 19, react-router 7, @tanstack/react-query, @tanstack/react-table, @tanstack/react-virtual, openapi-fetch + openapi-typescript, zustand (глобальный переключатель счетов), tailwindcss, shadcn/ui (radix), lucide-react, lightweight-charts, recharts, date-fns + date-fns-tz, zod, vitest, @testing-library/react, playwright (smoke).

**collector-mt5:** MetaTrader5, httpx, pydantic, pydantic-settings, structlog, tenacity.

Ограничение этого раздела касается **продуктовых** зависимостей. Сопутствующие инструментальные пакеты — плагины и конфиги линтеров, типы `@types/*`, сборочные плагины — следуют из требований 2.2 и отдельного согласования не требуют.

---

## 3. Модель данных

Все таблицы — в схеме `public`. Ниже — DDL‑эскиз; точные типы фиксируются в Alembic‑миграциях, которые являются источником истины после создания.

### 3.1 Пользователи и auth

```sql
users (
  id uuid pk,
  email citext unique not null,
  display_name text,
  timezone text not null default 'Europe/Moscow',   -- IANA
  day_boundary_hour smallint not null default 0,    -- час начала «торгового дня» в tz пользователя
  created_at timestamptz not null default now()
)

otp_codes (
  id uuid pk,
  email citext not null,
  code_hash text not null,          -- sha256(code + OTP_PEPPER)
  expires_at timestamptz not null,
  attempts smallint not null default 0,
  consumed_at timestamptz,
  created_at timestamptz not null default now()
)
index (email, created_at desc)

sessions (
  id uuid pk,                       -- значение cookie
  user_id uuid fk users not null,
  created_at timestamptz not null,
  expires_at timestamptz not null,
  last_seen_at timestamptz,
  user_agent text
)
```

### 3.2 Счета и секреты

```sql
trading_accounts (
  id uuid pk,
  user_id uuid fk users not null,
  label text not null,                       -- «Демо FTMO»
  is_demo boolean not null default false,
  color text not null,                       -- hex, из палитры 8 цветов
  platform text not null check (platform in ('mt5','csv','manual')),
  broker text,                               -- свободный текст
  server text,                               -- 'FTMO-Demo'
  login bigint,                              -- номер счёта MT5
  currency char(3) not null default 'USD' check (currency = 'USD'),  -- v1: только USD
  account_type text check (account_type in ('hedging','netting')),   -- определяется при первом синке
  server_utc_offset_minutes int,             -- последнее известное смещение сервера брокера
  status text not null default 'pending'
         check (status in ('pending','connected','needs_attention','paused','archived')),
  status_message text,                        -- человекочитаемая причина needs_attention
  sync_requested_at timestamptz,              -- ставит POST /accounts/{id}/sync-now (5.2); коллектор читает через assignments (5.6) и сравнивает с последним синком (8.2)
  last_sync_at timestamptz,
  last_heartbeat_at timestamptz,
  collector_id text,                          -- какой коллектор обслуживает
  sort_order int not null default 0,
  created_at timestamptz not null default now()
)
unique (user_id, platform, server, login) where platform = 'mt5'

account_credentials (
  account_id uuid pk fk trading_accounts on delete cascade,
  ciphertext bytea not null,                  -- envelope: AES-256-GCM(data_key, json{password})
  wrapped_data_key bytea not null,            -- AES-256-GCM(MASTER_KEY, data_key)
  key_version smallint not null,               -- НЕ счётчик: 15-битный отпечаток MASTER_KEY (blake2s), ADR-0003
  updated_at timestamptz not null
)
```

Правило: **пароль счёта не возвращается ни одним маршрутом API** и с `T-07` не читается вовсе — ни пользовательским запросом, ни выдачей коллектору (раздел 5.6). В терминал MT5 входит человек, коллектор подключается к открытому терминалу, и входить ему нечем и незачем — `docs/adr/0006-open-terminal-instead-of-passwords.md`.

Таблица `account_credentials` при этом остаётся, и остаётся необязательной: у счетов, заведённых до `T-07`, строка есть и обязана пережить обновление (миграции только вперёд‑совместимые, раздел 11.4). Поле `password` в теле `POST`/`PATCH /accounts` тоже осталось — необязательным входом без единого читателя; его удаление и удаление таблицы — второй шаг, отдельным релизом.

Формат блобов (S0‑05): оба поля самоописывающиеся — `версия раскладки (1 байт) | nonce (12) | AES‑256‑GCM | tag (16)`. В AAD входит `account_id`, поэтому шифротекст нельзя переставить в строку другого счёта. Открытый текст набивается до кратной длины: у GCM длина шифротекста равна длине открытого текста, иначе дамп БД выдаёт длину пароля.

`key_version` — **отпечаток мастер‑ключа, выведенный из его материала**, а не порядковый номер, которым управляет оператор. Колонка не может разойтись с реальностью, см. `docs/adr/0003-key-version-as-fingerprint.md`.

### 3.3 Сделки

```sql
deals (                                       -- факты от брокера, append-only
  id bigserial pk,
  account_id uuid fk trading_accounts not null,
  deal_ticket bigint not null,
  order_ticket bigint,
  position_id bigint not null,
  symbol_raw text not null,
  deal_type text not null,                    -- 'buy' | 'sell' | 'balance' | 'credit' | 'other'
  entry text not null,                        -- 'in' | 'out' | 'inout' | 'out_by'
  reason text,                                -- 'client' | 'expert' | 'sl' | 'tp' | 'so' | 'mobile' | 'web' | 'other'
  volume numeric(18,8) not null,
  price numeric(18,8) not null,
  profit numeric(18,2) not null,
  commission numeric(18,2) not null default 0,
  swap numeric(18,2) not null default 0,
  fee numeric(18,2) not null default 0,
  time_utc timestamptz not null,
  time_server timestamptz not null,           -- как пришло от терминала, для отладки
  comment text,
  magic bigint,
  raw jsonb not null,
  source text not null,                       -- 'collector' | 'ea' | 'csv' | 'manual'
  ingested_at timestamptz not null default now()
)
unique (account_id, deal_ticket)
index (account_id, position_id)
index (account_id, time_utc)

positions (                                   -- единица журнала, пересобирается из deals
  id uuid pk,
  account_id uuid fk trading_accounts not null,
  position_id bigint not null,                -- из MT5; для manual — генерируется отрицательный
  symbol_raw text not null,
  symbol_norm text not null,
  direction text not null check (direction in ('long','short')),
  status text not null check (status in ('open','closed')),
  open_time timestamptz not null,
  close_time timestamptz,
  volume_opened numeric(18,8) not null,       -- суммарный объём входов
  volume_closed numeric(18,8) not null,
  avg_entry_price numeric(18,8) not null,
  avg_exit_price numeric(18,8),
  gross_pnl numeric(18,2) not null default 0, -- сумма profit по deals
  commission numeric(18,2) not null default 0,
  swap numeric(18,2) not null default 0,
  fee numeric(18,2) not null default 0,
  net_pnl numeric(18,2) not null default 0,   -- gross + commission + swap + fee (все со знаком как у брокера)
  deals_count int not null,
  duration_seconds int,
  close_reason text,                          -- reason последнего out-deal
  is_manual boolean not null default false,
  rebuilt_at timestamptz not null
)
unique (account_id, position_id)
index (account_id, close_time)
index (account_id, symbol_norm)

symbols (
  id serial pk,
  raw text not null unique,                   -- 'EURUSD.m'
  norm text not null,                         -- 'EURUSD'
  asset_class text,                           -- 'fx' | 'metal' | 'index' | 'crypto' | 'energy' | 'stock' | 'other'
  digits smallint,
  contract_size numeric(18,4),
  tick_size numeric(18,8),
  source text not null default 'auto'         -- 'auto' | 'user' | 'seed'
)
```

Сборка позиций — раздел 7.

### 3.4 Пользовательский слой

```sql
journal_entries (
  position_id uuid pk fk positions on delete cascade,
  notes text,
  tags text[] not null default '{}',
  planned_entry numeric(18,8),
  planned_sl numeric(18,8),
  planned_tp numeric(18,8),
  risk_amount numeric(18,2),                  -- если задано — R считается от него
  updated_at timestamptz not null
)

reflections (
  position_id uuid pk fk positions on delete cascade,
  setup_grade text check (setup_grade in ('A','B','C','D')),
  execution_grade text check (execution_grade in ('A','B','C','D')),
  followed_plan boolean,
  emotion_before text,  emotion_during text,  emotion_after text,   -- словарь 3.5
  mistakes text[] not null default '{}',                             -- словарь 3.5
  confidence smallint check (confidence between 1 and 5),
  free_text text,
  filled_at timestamptz,
  updated_at timestamptz not null
)

attachments (
  id uuid pk,
  position_id uuid fk positions on delete cascade,
  s3_key text not null,
  content_type text not null,
  width int, height int, size_bytes int,
  created_at timestamptz not null
)

tags (                                        -- словарь тегов пользователя
  id uuid pk, user_id uuid fk users, name text not null, color text,
  unique (user_id, name)
)

sync_runs (
  id bigserial pk,
  account_id uuid fk trading_accounts,
  source text not null,
  started_at timestamptz not null,
  finished_at timestamptz,
  deals_received int default 0,
  deals_new int default 0,
  positions_rebuilt int default 0,
  server_utc_offset_minutes int,
  error text
)

daily_stats (                                 -- обычная таблица, точечно пересчитывается worker'ом (раздел 10); pk (account_id, day)
  account_id, day date (в tz пользователя с учётом day_boundary_hour),
  trades int, wins int, losses int, breakeven int,
  gross_pnl, net_pnl, commission, swap, volume
)
```

### 3.5 Словари (конфиг `apps/api/app/domains/journal/vocab.py`, отдаются фронту через `GET /api/v1/journal/vocab`)

```python
EMOTIONS = ["calm", "focused", "edgy", "fomo", "frustrated", "bored", "euphoric", "fearful", "tired"]
MISTAKES = [
  "no_plan", "early_entry", "late_entry", "chased", "moved_sl", "no_sl", "oversized",
  "revenge", "early_exit", "held_too_long", "against_trend", "news_ignored", "overtrading",
]
SETUP_GRADES = EXECUTION_GRADES = ["A", "B", "C", "D"]
```

Русские подписи — на фронте в `ru.ts`. Ключи стабильны, не переименовывать.

---

## 4. Аутентификация и сессии

Поток:

1. `POST /api/v1/auth/request-code {email}` → создаёт `otp_codes` (6 цифр, TTL 10 мин), отправляет письмо через `EmailProvider`. Ответ всегда `202` независимо от существования email.
   Rate‑limit (Redis): 3 запроса / 10 мин на email, 10 / час на IP. При превышении — `429` с `retry_after`.
2. `POST /api/v1/auth/verify {email, code}` → ищет последний непогашенный код; при неверном — `attempts += 1`, после 5 — код погашен; при верном — создаёт `users` при отсутствии, создаёт `sessions`, ставит cookie.
3. Cookie `td_session`: `HttpOnly; Secure (в prod); SameSite=Lax; Path=/; Max-Age=30d`. Значение — `sessions.id`. Скользящее продление: если `last_seen_at` старше 1 дня — обновить и продлить `expires_at`.
4. `POST /api/v1/auth/logout` — удаляет сессию, чистит cookie.
5. `GET /api/v1/auth/me` → `{id, email, display_name, timezone, day_boundary_hour}`; `401` если нет сессии.

`EmailProvider` — интерфейс `send(to, subject, text, html)`; реализации: `ConsoleEmailProvider` (пишет в лог + в таблицу `dev_outbox`, видна на странице `/dev/outbox` только при `APP_ENV=local`), `ResendEmailProvider`. Выбор — `EMAIL_PROVIDER=console|resend`.

CSRF: SPA и API на одном origin (через прокси), `SameSite=Lax` + проверка заголовка `Origin` на мутирующих запросах. Дополнительный CSRF‑токен не нужен.

---

## 5. HTTP API

### 5.1 Общее

- Все ответы JSON. Ошибка:
  ```json
  {"error": {"code": "account_not_found", "message": "Счёт не найден", "details": {}}}
  ```
  Коды HTTP: 400 валидация (`validation_error`, `details.fields`), 401 `unauthorized`, 403 `forbidden` и `forbidden_origin` (чужой `Origin` на мутирующем запросе, раздел 4), 404 `not_found`, 409 `conflict`, **413 `payload_too_large`** (батч больше 5 000 сделок и тело сверх потолка — раздел 5.3), 422 бизнес‑правило (`unprocessable_entity` и доменные коды), 429 `rate_limited`.

  Порождаются не доменом, но фронт обязан их знать: 405 `method_not_allowed` (роутер), 500 `internal_error` — наружу уходит только код и общее сообщение, текст исключения не выходит никогда.

  Объявлены без производителя, на будущее: 409 `conflict`, 415 `unsupported_media_type` (появится с загрузкой вложений в S2‑04). Проверено, что FastAPI 415 не порождает сам.

  Весь этот набор объявлен в OpenAPI глобально, специфичные доменные коды — на своих эндпоинтах. Решение и его цена — `docs/adr/0004-openapi-error-contract.md`.
- Пагинация списков — курсорная: `?limit=50&cursor=…`, ответ `{"items": [...], "next_cursor": "…"|null}`.
- Время в API — ISO 8601 с `Z`. Фронт переводит в tz пользователя.
- Фильтр по счетам во всех пользовательских списках: `?account_ids=uuid,uuid` (пусто = все не архивированные счета пользователя).

### 5.2 accounts

| Метод | Путь | Описание |
|---|---|---|
| GET | `/accounts` | Список счетов пользователя с статусом, `last_sync_at`, `last_heartbeat_at`, счётчиком позиций |
| POST | `/accounts` | Создать. Тело: `{label, is_demo, color, platform, broker?, server?, login?, password?}`. Для `mt5` обязательны `server, login`. **`password` необязателен и устарел** (`T-07`): счёт заводится без него, а присланное значение шифруется и никем не читается. Статус `pending` |
| PATCH | `/accounts/{id}` | `label, is_demo, color, sort_order, broker` (явный `null` очищает брокера); для mt5 — `server, login` (**изменение** значения возвращает статус в `pending`: это другой счёт у брокера) и устаревший `password` — он перезаписывает credentials и статуса не трогает (`T-07`) |
| POST | `/accounts/{id}/pause` / `/resume` | `paused` ↔ `pending` |
| POST | `/accounts/{id}/archive` | Скрывает из переключателя; credentials удаляются; сделки остаются |
| DELETE | `/accounts/{id}` | Полное удаление со всеми deals/positions (подтверждение на фронте по имени счёта) |
| POST | `/accounts/{id}/sync-now` | Ставит флаг `sync_requested_at`; коллектор подхватывает на следующем heartbeat |
| GET | `/accounts/{id}/sync-runs` | Последние 50 `sync_runs` |

### 5.3 ingest (для коллектора, советника, CSV — единый вход)

`POST /ingest/deals` — заголовок `Authorization: Bearer <token>`, где token — либо сервисный токен коллектора (`COLLECTOR_TOKEN`), либо персональный ключ счёта (`account_ingest_keys`, этап 4 для советника).

⚠️ **Сервисный токен глобален для установки: он даёт запись в любой её счёт, а не только в закреплённые за этим коллектором.** Проверить принадлежность нечем — батч не несёт `collector_id`, и эндпоинт не знает, кто говорит (в отличие от 5.6, где `collector_id` приходит параметром). Границей это не было бы и с проверкой: держатель токена и так может закрепить за собой любой свободный счёт через assignments. Настоящая изоляция — `X-52`, и делать её дешевле до `S1-08`, пока отправителя не написали.

Тело — по `packages/shared-schemas/ingest-deals.schema.json`:

```json
{
  "account_id": "uuid",
  "source": "collector",
  "server_utc_offset_minutes": 180,
  "account_info": {"currency": "USD", "margin_mode": "hedging", "balance": 10000.0, "equity": 10012.5},
  "deals": [
    {
      "ticket": 123456789, "order": 123456700, "position_id": 123456700,
      "symbol": "EURUSD.m", "type": 0, "entry": 0, "reason": 3,
      "volume": 0.10, "price": 1.08543, "profit": 0.0, "commission": -0.35, "swap": 0.0, "fee": 0.0,
      "time_server": "2026-09-02T14:03:11", "time_msc": 1788357791123,
      "comment": "", "magic": 0
    }
  ],
  "open_positions": [ { "position_id": 1, "symbol": "XAUUSD", "type": 0, "volume": 0.5, "price_open": 2410.1, "time_server": "…", "sl": 2400.0, "tp": 2450.0, "profit": 12.3 } ]
}
```

Поведение:

1. Батч ≤ 5 000 deals, иначе `413`.
2. Вставка `deals` через `INSERT … ON CONFLICT (account_id, deal_ticket) DO NOTHING`. `time_utc = time_server − offset` (см. раздел 6.3). `deal_type/entry/reason` маппятся из чисел MT5 (раздел 6.2).
3. Обновляются `trading_accounts.account_type` (по `margin_mode`), `server_utc_offset_minutes`, `last_sync_at`, `status='connected'`.
4. Для всех `position_id`, затронутых новыми deals, плюс всех из `open_positions`, — пересборка позиций (раздел 7) в той же транзакции.
5. Открытые позиции без deals (например, история ещё не догружена) создаются как `status='open'` из `open_positions`; при появлении deals пересобираются.
6. Ставится задача worker'у `refresh_daily_stats(account_id, within)`, где `within` — отрезок `time_utc` тронутых сделок. Дни внутри отрезка считает сама задача: день режется по зоне и `day_boundary_hour` **владельца** счёта (§2 `docs/metrics.md`), а ингест приходит по сервисному токену установки и владельца не видит — посчитай он дни здесь, правило торгового дня получило бы второе прочтение.
7. Ответ: `{"received": N, "inserted": M, "duplicates": N-M, "positions_rebuilt": K, "sync_run_id": …}`.

`POST /ingest/heartbeat` — `{collector_id, accounts: [{account_id, state: "running"|"error"|"stopped", message?, terminal_login?}]}`; обновляет `last_heartbeat_at`, `status` (`error` → `needs_attention` + `status_message`).

### 5.4 journal

| Метод | Путь | Описание |
|---|---|---|
| GET | `/journal/positions` | Фильтры: `account_ids, status, from, to, symbol, direction (long/short), result (win/loss/be), tags, has_reflection (bool), q`. Сортировка `sort=close_time:desc` (поля: close_time, open_time, net_pnl, symbol_norm, duration_seconds). Ответ — позиция + `journal_entry` (кратко) + `reflection.filled_at` + `attachments_count` + `account {id,label,color,is_demo}`. ⚠️ `result='be'` считается **точным нулём** `net_pnl`: на счетах с комиссией он практически всегда пуст, и фронт вправе не показывать его отдельным чипом |
| GET | `/journal/positions/{id}` | Полная карточка: позиция, deals позиции, journal_entry, reflection, attachments (с presigned GET URL, TTL 1 ч). ⚠️ `attachments` появляется в `S2-04`; до него карточка отдаёт только `attachments_count` |
| PUT | `/journal/positions/{id}/entry` | Заметки, теги, planned_*, risk_amount. ⚠️ Тело требует **все** поля: `PUT` заменяет запись целиком, и частичное тело автосохранения иначе стирало бы заметку молча, отвечая `200`. Отсутствующее поле — `400 validation_error`, очистка — явный `null` (у `tags` — пустой массив). Незнакомый тег заводится в словаре сам, без цвета; написание в ответе берётся из словаря и может отличаться от присланного регистром |
| PUT | `/journal/positions/{id}/reflection` | Все поля рефлексии, и все обязательны — как у `entry`. `filled_at` ставится при первом сохранении с хотя бы одним заполненным полем, **не переставляется** последующими правками (когда разобрал ≠ когда трогал, второе — `updated_at`) и **снимается**, если рефлексию очистили целиком, иначе `has_reflection=true` возвращал бы пустую. Заполнено = человек сделал выбор: `followed_plan=false` — заполнено, пустая строка и пустой массив — нет |
| POST | `/journal/positions/manual` | Ручная сделка: `{account_id, symbol, direction, open_time, close_time?, volume, entry_price, exit_price?, commission?, swap?, net_pnl?}` → создаётся `positions` с `is_manual=true`, `position_id` отрицательный (sequence) и один синтетический deal |
| PATCH/DELETE | `/journal/positions/{id}` | Только для `is_manual=true`; иначе `422 not_manual` |
| POST | `/journal/positions/{id}/attachments/presign` | `{content_type, size_bytes}` → `{upload_url, s3_key, attachment_id}`; лимит 10 МБ, `image/png|jpeg|webp` |
| POST | `/journal/positions/{id}/attachments/{attachment_id}/confirm` | После успешной загрузки; `{width, height}` |
| DELETE | `/journal/attachments/{id}` | |
| GET | `/journal/tags` / POST / DELETE | Словарь тегов. `GET` → `{items: [{id, name, color, usage_count}]}`; `usage_count` нужен подтверждению удаления, иначе человек соглашается вслепую. ⚠️ `POST` — **upsert, а не только создание**, и отвечает `200`: тег с тем же именем без учёта регистра — он же самый, `409` не бывает. Это единственное место, где меняется написание тега, и смена **переписывает его на всех позициях** пользователя; иначе исправить регистр можно было бы только удалением. ⚠️ `DELETE` **снимает тег со всех позиций** и возвращает `{name, positions_updated}`: оставленный на позициях тег вернулся бы в словарь сам при первом же автосохранении такой карточки. Уникальность имён — без учёта регистра, но держится **кодом**, а не индексом (в 3.4 стоит `unique (user_id, name)`). ⚠️ И смена написания, и удаление двигают `updated_at` у затронутых записей журнала: содержимое `journal_entries.tags` действительно изменилось. Клиенту, который сверяется с `updated_at` (автосохранение карточки в `S2-07`), после этих двух операций надо перечитать открытые карточки |
| GET | `/journal/vocab` | Словари раздела 3.5 |
| GET | `/journal/calendar?month=2026-09&account_ids=` | `{month, timezone, day_boundary_hour, days: [{day, starts_at, ends_at, trades, wins, losses, breakeven, net_pnl, by_account: [{account_id, net_pnl, trades}]}]}`. Дни без закрытых позиций не возвращаются. ⚠️ Границы дня (`starts_at`/`ends_at`) приходят с сервера, и клик по дню открывает журнал **ими же**: правило торгового дня живёт на сервере одним выражением, и второй его реализации на клиенте быть не должно — иначе календарь покажет сделку в понедельник, а журнал за понедельник её не найдёт |

Правило: `result` считается по `net_pnl`: `> 0` win, `< 0` loss, `= 0` breakeven.

### 5.5 analytics (этап 3, в v1 — только календарь и summary)

`GET /analytics/summary?account_ids=&from=&to=` → `{trades, wins, losses, breakeven, open_positions, winrate, net_pnl, gross_pnl, commission, swap, fee, profit_factor, avg_win, avg_loss, expectancy, best_trade, worst_trade}`. Формулы, краевые случаи и примеры с числами — `docs/metrics.md`. Используется в шапке журнала.

`breakeven` и `fee` добавлены в `S2-05` сверх первоначального перечня: без них на экране не сходятся `trades = wins + losses + breakeven` и `net_pnl = gross_pnl + commission + swap + fee`, и человек видит арифметику, которая не бьётся.

⚠️ **Сделка здесь — закрытая позиция**, и все денежные суммы считаются по тому же множеству. Значит сводка **не сойдётся** с суммой колонки журнала, когда в списке видны открытые позиции; разница равна сумме их `net_pnl`, а сколько их — говорит `open_positions`. Точное совпадение даёт фильтр `status=closed`. Причина не косметическая: у открытой позиции в `net_pnl` лежат накопленные издержки, а не плавающий результат (§7) — по тому же основанию `S2-01` не показывает у открытой позиции `result`.

Счётчики отдаются числами, всё дробное — строками. `null` возможен у `winrate`, `profit_factor`, `avg_win`, `avg_loss`, `expectancy`, `best_trade`, `worst_trade`: «нечего считать» и «ноль» — разные утверждения, и `profit_factor` без единого убытка это лучший возможный результат, а не худший.

### 5.6 internal (только сервисный токен коллектора)

- `GET /internal/collector/assignments?collector_id=` → `{items: [{account_id, server, login, sync_requested_at, last_sync_at, status}]}` для счетов со статусом `pending|connected|needs_attention` и `collector_id in (null, this)`. При выдаче `collector_id` фиксируется за счётом.

  ⚠️ **Пароля в ответе нет** (`T-07`, ADR‑0006). `login` при этом стал рабочим полем, а не справочным: коллектор сверяет им счёт, открытый в терминале человеком, — подключение идёт к чужому по отношению к нам процессу, и без сверки в журнал молча попали бы сделки другого счёта. Наличие или отсутствие сохранённых credentials на выдачу не влияет: счёт без пароля — норма.

  Конверт `{items}`, а не голый массив (решено в `S1-05`, до появления потребителя): расширять голый массив некуда, а курсорная пагинация из 5.1 добавляется полем рядом с `items` вместо ломающей правки формы. Та же форма, что у списков в 5.2 и 5.7.
- Ответ шифруется TLS в проде; локально — localhost. Логируется **закрепление** счёта за коллектором (`account_id`, `collector_id`, время) — событие `collector.accounts_claimed`. Раньше это был журнал выдачи пароля, по строке на счёт за каждый запрос; выдавать перестали, а запись оставили той, у которой остался предмет: assignments опрашивается раз в минуту, и строка на счёт за тик была бы шумом, в котором это же событие и потерялось бы.

### 5.7 users и system

- `GET /users/me` — то же, что `auth/me` (общая модель ответа, не копия); `PATCH /users/me {display_name?, timezone?, day_boundary_hour?}` — частичный, лишние поля запрещены; таймзона валидируется по IANA, час 0–23.
- `GET /users/timezones` → `{items: string[]}` — имена IANA, отсортированы, **ровно то множество, которое принимает `PATCH`**. `ETag` + `Cache-Control: private, no-cache`, отдаёт `304` на условный запрос.

  ⚠️ Список обязан приходить с сервера, а не из `Intl.supportedValuesOf` браузера. Образ API несёт tzdata **без backward‑ссылок** и принимает только канонические имена, а ICU браузера для части зон считает каноническим legacy‑имя (`Asia/Calcutta`, `Europe/Kiev`, `Asia/Saigon`). Из-за расхождения пользователи Индии, Украины, Вьетнама, Непала, Мьянмы, Гренландии, Фарер и Аргентины не могли сохранить свою зону вовсе — найдено ревью `S0-08`. Согласованность двух списков закрыта тестом: каждое отдаваемое имя проверяется настоящим `PATCH`.

  `Factory` и `localtime` из набора исключены: первое в самой tzdata означает «зона не настроена», второе — ссылка на настройку конкретной машины и меняет смысл вместе с образом.
- `GET /users/me/export` — ставит задачу `export_user_data`, возвращает `{job_id}`; `GET /users/me/export/{job_id}` → `{status, download_url?}`.
- `GET /health` → `{status, db, redis, version}`; `GET /version`.

---

## 6. Нормализация deals из MT5

### 6.1 Что забирает коллектор

`mt5.history_deals_get(from, to)` — все deals; `mt5.positions_get()` — открытые; `mt5.account_info()` — `currency`, `margin_mode` (0 retail netting, 1 exchange, 2 retail hedging), `balance`, `equity`; `mt5.terminal_info()`; время сервера — `mt5.symbol_info_tick(any_symbol).time` либо разница `time_msc` последнего deal с локальным UTC (см. 6.3).

### 6.2 Маппинг перечислений

| MT5 | Поле | Значения |
|---|---|---|
| `DEAL_TYPE_BUY=0`, `SELL=1` → `buy/sell`; `BALANCE=2 → balance`; `CREDIT=3 → credit`; всё остальное (`CHARGE, CORRECTION, BONUS, COMMISSION*, INTEREST, …`) → `other` | `deal_type` | |
| `DEAL_ENTRY_IN=0 → in`, `OUT=1 → out`, `INOUT=2 → inout`, `OUT_BY=3 → out_by` | `entry` | |
| `DEAL_REASON_CLIENT=0 → client`, `MOBILE=1 → mobile`, `WEB=2 → web`, `EXPERT=3 → expert`, `SL=4 → sl`, `TP=5 → tp`, `SO=6 → so`, прочие → `other` | `reason` | |

Deals с `deal_type in (balance, credit, other)` сохраняются в `deals` (для сверки баланса), но **не участвуют** в сборке позиций, кроме случая `other` с `position_id ≠ 0` (комиссии/корректировки по позиции) — их `profit/commission/swap/fee` прибавляются к позиции.

### 6.3 Время

- `time_server` — naive‑время сервера брокера, как отдаёт терминал (`datetime.fromtimestamp(deal.time, tz=UTC)` даёт «фальшивый UTC», равный серверному времени; трактуем его как серверное).
- Смещение сервера: коллектор вычисляет `offset = round((server_now − utc_now) / 15 min) * 15 min`, где `server_now` — `symbol_info_tick(...).time` по ликвидному символу в рабочее время; вне рабочего времени — последнее известное. Шлёт в каждом батче.
- `time_utc = time_server − offset`. Сохраняем оба. Смещение записывается в `sync_runs` — при смене (DST) прошлые deals не пересчитываются, они уже в UTC.
- Отображение: `time_utc` → tz пользователя. «Торговый день» позиции = дата `close_time` (для открытых — `open_time`) в tz пользователя со сдвигом `day_boundary_hour`.

### 6.4 Символы

При первом появлении `symbol_raw`: поиск в `symbols` по `raw`; если нет — эвристика: верхний регистр, убрать суффиксы по регулярному выражению `[._-](m|micro|mini|c|cent|pro|ecn|raw|std|i|\+|#|\d+)$` (итеративно), затем сверка со словарём известных символов (seed: мажоры, кроссы, XAUUSD/XAGUSD, US30/US100/US500/DE40/UK100/JP225, BTCUSD/ETHUSD, USOIL/UKOIL); `asset_class` — по словарю; при провале `norm = очищенный raw`, `asset_class='other'`. Пользователь может поправить через UI (этап 4); `source='user'` не перезаписывается автоматикой.

---

## 7. Сборщик позиций (`position_builder.py`)

Вход: все deals с данным `(account_id, position_id)`, отсортированные по `(time_utc, deal_ticket)`, плюс необязательная запись из `open_positions`. Выход: одна строка `positions`. Функция **чистая** (без I/O), покрыта тестами на фикстурах.

Алгоритм (хеджинговый и неттинговый счёт обрабатываются одинаково, потому что в MT5 `position_id` уже уникален для обоих режимов; различие — только в том, что на неттинге `inout` deal переворачивает позицию):

```
direction  = по первому deal с entry in (in, inout): buy → long, sell → short
opened     = Σ volume deals с entry=in (+ inout: часть, открывающая новую сторону)
closed     = Σ volume deals с entry in (out, out_by) (+ inout: часть, закрывающая)
avg_entry  = Σ(price×volume входов) / opened
avg_exit   = Σ(price×volume выходов) / closed, если closed > 0
gross_pnl  = Σ profit по всем deals позиции (включая 'other' с этим position_id)
commission = Σ commission; swap = Σ swap; fee = Σ fee
net_pnl    = gross_pnl + commission + swap + fee
status     = 'closed' если |opened − closed| < 1e-8 и нет записи в open_positions, иначе 'open'
open_time  = time_utc первого входа; close_time = time_utc последнего выхода при status=closed
close_reason = reason последнего deal с entry in (out, out_by)
deals_count = число торговых deals (buy/sell)
duration_seconds = close_time − open_time
```

`inout` на неттинге: deal объёмом V при текущей открытой позиции P противоположного направления закрывает P и открывает V−P в новом направлении. Для v1: позиция закрывается (`closed += P`), а остаток V−P **не** создаёт новую позицию в нашей модели, потому что MT5 при переворотe назначает новый `position_id` — новая позиция придёт своими deals. Тест на это обязателен.

Частичные закрытия: несколько `out` deals — одна позиция, `avg_exit` взвешенный. Тест обязателен.

Пересборка идемпотентна: повторный вызов на тех же deals даёт ту же строку (`UPSERT` по `(account_id, position_id)`), пользовательский слой (`journal_entries`, `reflections`, `attachments`) не трогается, потому что привязан к `positions.id`, который при UPSERT сохраняется.

Тестовые фикстуры (`tests/fixtures/deals/*.json`, обезличенные, описаны в `docs/fixtures.md`): простая long‑сделка; short с SL; частичное закрытие в 3 приёма; доливка + закрытие; переворот на неттинге; позиция с корректировкой `other`; открытая позиция без выхода; deals, пришедшие в двух батчах с перекрытием.

---

## 8. Коллектор MT5 (`apps/collector-mt5`)

**Терминал открывает человек, коллектор к нему подключается** (решено в `T-07` по итогам `X-66`; ADR пишется там же). Коллектор не запускает MetaTrader 5, не делает его копий и не входит в счёт паролем: человек сам открывает терминал и входит в счёт, а коллектор спрашивает у терминала, какой счёт в нём открыт, и синхронизирует именно его. Остальные счета ждут, пока человек в них не войдёт.

Причина — измерение на живой машине 10 сентября 2026 (Windows 10 22H2, MT5 build 6182): `initialize(path=<копия>, portable=True, login=…, password=…, server=…, timeout=60000)` возвращал `(-10005, 'IPC timeout')` **всегда** — десятки попыток, четыре прогона, оба счёта, — а `initialize()` без аргументов к тому же самому терминалу отвечал `True` мгновенно, с чтением счёта и истории. Цена решения названа и принята: **синхронизируется только открытый счёт.** Данные при этом не теряются — окно выборки идёт от `last_sync_at`, и счёт догоняет пропущенное целиком, когда в него войдут.

### 8.1 Конфигурация (`collector.env`)

```
API_URL=http://localhost:8000
COLLECTOR_TOKEN=…                     # совпадает с api
COLLECTOR_ID=nikita-laptop
SYNC_INTERVAL_SECONDS=60
HEARTBEAT_INTERVAL_SECONDS=60
FIRST_SYNC_DAYS=3650
LOG_LEVEL=INFO
LOG_DIR=logs                          # необязательное; под Планировщиком заданий рабочей
                                      # папкой легко оказывается системный каталог
STATE_DIR=state                       # необязательное; смещение часов брокера, файл на счёт
```

**Путей к терминалу в настройках нет** (`X-66`): `MT5_TERMINAL_EXE` и `MT5_PORTABLE_ROOT` убраны вместе с механизмом копий, `MAX_ACCOUNTS` — вместе с пулом процессов. Уже собранные `collector.env` эти строки содержат, и коллектор из-за них не падает: неизвестные ключи игнорируются (`extra="ignore"`), они просто перестают что-либо значить. Папку `C:\td-terminals` с копиями терминала можно удалить.

**Пароль счёта коллектору не нужен** (`T-07`): в терминал он не входит. `login` и `server` из assignments — это не «чем войти», а **чем сверить** (§8.2, пункт 4).

### 8.2 Поведение

Процесс один: один канал `MetaTrader5` на машину, один открытый терминал, один синхронизируемый счёт. Точка входа — `python -m collector.main`.

1. **Тик цикла — меньший из двух интервалов**, `min(SYNC_INTERVAL_SECONDS, HEARTBEAT_INTERVAL_SECONDS)`. Цикл один, а интервала в настройках два, и оба означают своё: первый — как часто спрашивать терминал, второй — как часто отмечаться у TradeDesk (молчание дольше пяти минут уводит счёт в «коллектор не на связи», §10). Каждый тик коллектор вызывает `GET /internal/collector/assignments`, опознаёт открытый счёт и шлёт heartbeat; терминал за историей он при этом спрашивает не чаще, чем велит `SYNC_INTERVAL_SECONDS`. Взять один интервал и забыть второй значило бы оставить в `collector.env` поле-обманку.
2. Молчание API прежний список счетов не отменяет: одна неудачная минута иначе снимала бы счета с наблюдения. Счетов нет вовсе — строка в лог: отправлять heartbeat не за кого.
3. Подключение — `mt5.initialize(timeout=60000)`, **без пути, без `portable`, без входа в счёт**. Отказ — `heartbeat state=error` с человекочитаемой причиной («MetaTrader 5 не открыт или не отвечает коллектору. Откройте терминал, войдите в счёт…») и повтор на следующем тике. Экспоненциальной задержки здесь нет намеренно: отказ означает «человек ещё не открыл терминал», и ждать четверть часа после того, как он его открыл, — худший из возможных ответов.
4. **Сверка счёта — обязательная, и она делается дважды.** Сразу после подключения коллектор спрашивает `account_info()` и сверяет `login` **и** `server` с заданием:
   - совпали оба — этот счёт синхронизируется;
   - совпал только `login` — синхронизации нет, а на карточке **этого** счёта появляется расхождение с обоими именами сервера: номера демо-счетов у разных брокеров пересекаются, и совпадение по одному логину означало бы историю чужого счёта в чужом журнале;
   - логина нет среди счетов коллектора — синхронизации нет, и причина уходит на карточки **всех** счетов: терминал открыт, коллектор жив, а сделок не будет, и человек обязан прочитать почему;
   - подошло **больше одного** счёта — синхронизации нет ни у одного, и причина тоже уходит всем. Взять первый значило бы, что журнал выбирает порядок ответа assignments: уникальность в БД сравнивает имя сервера посимвольно (§3.2), а коллектор — без регистра, так что «E-Global-Real» и «e-global-real» с одним логином заводятся оба, а для терминала это один и тот же счёт.
   Вторая сверка стоит **после** чтения истории, перед отправкой: человек вправе переключить счёт в терминале одним щелчком, и тогда батч выбрасывается целиком с текстом «счёт в терминале сменился». Первая проверка отвечает на вопрос «чей счёт мы спросили», вторая — «чей счёт нам ответил». Без второй сделки чужого счёта уехали бы в чужой журнал молча, а `deals` — append-only факты (§5.3, §7).
5. Синхронизация открытого счёта:
   - первый синк: `history_deals_get(now − FIRST_SYNC_DAYS, now + 1 day)`, батчами по 5 000 в хронологическом порядке;
   - далее каждый тик: `history_deals_get(last_sync_at − 24h, now + 1 day)` + `positions_get()` + `account_info()`; отправка только если есть deals новее последнего отправленного тикета **или** изменился набор открытых позиций **или** прошло 10 минут (чтобы обновить `last_sync_at`);
   - `sync_requested_at` из assignments новее последнего синка → внеочередной полный синк за 30 дней;
   - проверка `account_info().currency != 'USD'` → `heartbeat state=error, message="Счёт не в USD"`, синк не выполняется (v1).
6. **Heartbeat уходит за все счета сразу, каждый тик.** Открытый счёт получает своё состояние; счёт, который ждёт своей очереди, — `state=running` **без сообщения**. Молчание здесь решение, а не забывчивость: `state=error` — единственный способ написать текст на карточку, и он же красит её в «требует внимания» (§5.3). Ожидание своей очереди — **штатное** состояние новой схемы, и три карточки из четырёх, вечно требующие внимания, сделали бы этот статус нечитаемым. Чем счёт занят на самом деле, видно по `last_sync_at` на той же карточке. `state=error` для всех сразу остаётся там, где не синхронизируется **ни один**: терминал не открыт или открыт на чужом счёте.
7. Логи — structlog в файл с ротацией, **один файл** `logs/collector.log`: процесс один, делить его не с кем. В логах никогда нет секретов. Числовой код и описание от библиотеки уезжают в лог отдельными полями `mt5_code` и `mt5_description` (`X-67`) — на карточку счёта код не тащится, там человеку нужен смысл, а не число; в файле лога, который человек присылает разработчику, нужно ровно обратное: диагноз `X-66` занял час именно потому, что кода в логе не было.
8. Установка (`S1-10`): `run-collector.bat` — проверка версии Python, `.venv`, `pip install -e .[mt5]`, сборка `collector.env` и запуск; `install-service.ps1` — регистрация в Планировщике заданий «при входе в систему», перезапуск при сбое, явная рабочая папка; `install-service.bat`, `stop-collector.bat` и `status-collector.bat` — то же двойным кликом. Сценарии ручной проверки собраны в `docs/collector-windows-checklist.md`.

**Ни к чему из этого коллектор не идёт через системный прокси** (решено в `X-68`): у клиента `httpx` стоит `trust_env=False`. По умолчанию `httpx` читает `HTTP_PROXY`, `HTTPS_PROXY` и системные настройки прокси Windows, а VPN на машине трейдера — норма и прописывает себя системным прокси: у первого пользователя запросы к `http://localhost:8000` уходили в туннель и возвращались `502 Bad Gateway`, то есть симптомом «сервер сломался» при здоровом сервере. Лазейки «а вдруг TradeDesk за прокси» нет: §8.1 знает только локальную установку, появится удалённая — появится своё решение.

**Версия Python названа и проверяется** (решено в `S1-10`; требование DoD §12). Нужен ровно **3.12** — тот, что стоит в `.python-version` и который гоняет гейт; `run-collector.bat` на любой другой версии отказывается работать и печатает, что скачать и куда нажать. Пакет требует `>=3.12`, и колёса `MetaTrader5` для 3.13 и 3.14 существуют, но прогонов на них нет ни одного, а машина пользователя — та, до которой мы не дотянемся. Осознанный выход за проверенное оставлен переменной `TD_ALLOW_ANY_PYTHON`, и он называет себя предупреждением на экране.

**Зависимости ставятся при первом запуске и после обновления продукта, а не при каждом старте** (решено в `S1-10`). `pip` зовётся при первом запуске и после того, как изменился `pyproject.toml` — сверка побайтовая, с копией в `.venv`. Иначе автозапуск после перезагрузки зависел бы от интернета и от доступности PyPI, то есть коллектор не поднимался бы ровно тогда, когда связь и так плохая.

**`COLLECTOR_TOKEN` переносится в `collector.env` из `.env` установки** (решено в `S1-10`, `collector/bootstrap.py`). Человек иначе копирует 64 символа глазами, а ошибка в них выглядит как «TradeDesk не отвечает» через минуту работы. Значение при этом не печатается ни в консоль, ни в файл лога. **Первый запуск на созданном файле больше не останавливается** (`X-66`): останов был нужен ради двух решений человека — путь к терминалу и `MAX_ACCOUNTS`, — и оба поля из настроек ушли. Вместо остановки скрипт говорит то единственное, что от человека теперь нужно: открыть MetaTrader 5 и войти в счёт. Без токена остановка остаётся — без него коллектор получит `401`.

**Остановка — `stop-collector.bat`, и это часть контракта, а не удобство** (решено в `S1-10`). Сначала коллектор **просят** выйти самому: скрипт кладёт рядом с `collector.env` файл `collector-stop.flag`, коллектор видит его своим тиком и уходит обычным путём — через `_shutdown`: отпускает канал к терминалу и шлёт `state=stopped`. Просьба именно файлом, потому что доставить сигнал чужому процессу на Windows нечем: `SIGTERM` там не межпроцессный, а `CTRL_BREAK` требует присоединения к консоли жертвы. Ждать бесконечно нельзя — тик с недоступным API тянется минутами, — поэтому потолок 20 секунд, а дальше гасится задача Планировщика и сам процесс. **Окно MetaTrader 5 остановка не закрывает и закрывать не вправе**: терминал открыл человек и в нём торгует.

⚠️ **Мягкая остановка обещанием быть не может.** Успела она или нет, зависит от того, где коллектор был в момент просьбы, и проверить это на Windows пока некому. Поэтому скрипт печатает не обещание, а результат: успел — «он успел попрощаться», не успел — «остановлен принудительно», и тогда же говорит цену. Принудительная остановка до `_shutdown` не доходит: прощальный `state=stopped` не уходит. **Карточки счетов два исхода не различают, и обещать обратное скрипт не вправе** (`X-62`): `state=stopped` не меняет ни статуса, ни текста (§5.3), а состояния «коллектор остановлен» в перечне §9.3 нет вовсе — после любой остановки на карточках сразу не меняется ничего, а через пять минут `check_collectors` (§10) пишет там «коллектор не на связи», то есть вид поломки после осознанного действия. Данные при этом не теряются: `last_sync_at` двигает только принятый батч, а следующий запуск забирает своё окно целиком.

**Кодировка файлов установки задана и закреплена тестом** (решено в `S1-10`, закрывает `X-55` для файлов коллектора). `.bat` — UTF-8 **без** BOM, переводы строк CRLF, `chcp 65001` первой командой; `.ps1` — UTF-8 **с** BOM. Русская консоль Windows читает `.bat` в CP866, а Windows PowerShell 5.1 читает файл без BOM как CP1251: в обоих случаях первое же сообщение коллектора оказалось бы нечитаемым, а оно и есть единственный канал диагностики на чужой машине. `run-collector.bat` дополнительно выставляет `PYTHONUTF8=1`: без него `print()` русской строки в консоли CP866 падает с `UnicodeEncodeError`, а `structlog` заваливает экран сообщениями `--- Logging error ---` вместо строк лога.

**Строка, которую граница отвергнет, не отправляется** (решено в `S1-08`). Коллектор проверяет то же, что и `S1-01`, — пробел в символе, расхождение `time`/`time_msc`, `entry` вне 0..3 — и такую сделку в батч не кладёт. Причина: батч отвергается целиком, и одна испорченная сделка остановила бы синхронизацию счёта **навсегда**, потому что из истории она никуда не денется. Потеря не молчаливая: тикет и причина уходят в лог и в heartbeat. **То же и с открытыми позициями** (`type` вне 0|1, пустой символ, отрицательный объём): они едут в каждом батче окна, поэтому одна негодная останавливала бы не один батч, а все подряд. Отброшенная запись `open_positions` позицию не закрывает — `status` считается ещё и по балансу объёмов (§7). `account_info` выбросить нельзя: непереводимое значение там (неизвестный `margin_mode`) останавливает синк счёта с названной причиной, а не роняет процесс.

**Смещение часов брокера принимается только после подтверждения** (решено в `S1-08`, уточняет §6.3). Первое значение в батч не уезжает и на диск не пишется: коллектор ждёт второго расчёта по **обновившейся** котировке (у застывшего тика время не меняется, и повтор ничего не доказывает). Причина: одна протухшая котировка на тонком рынке даёт правдоподобное смещение, а `time_utc` прошлых сделок не пересчитывается — испорченным оказался бы весь журнал счёта. Цена — один цикл опроса на первом в жизни счёта запуске; дальше значение живёт в `STATE_DIR`, файлом на счёт: смещение у каждого брокера своё, и один общий файл сложил бы разные смещения в одно значение.

**Пула процессов больше нет** (решено в `X-66`, отменяет решения `S1-09` о `MAX_ACCOUNTS`, местах в пуле, политике перезапусков и кодах выхода 4). Канал `MetaTrader5` один на машину: `initialize()` без пути цепляется к тому экземпляру, который найдёт, а `shutdown()` из второго процесса рвёт соединение первого. Пул процессов над одним каналом означал бы N попыток отобрать его друг у друга — и ни одного способа проверить это до Windows. Вместе с пулом ушли `multiprocessing`, сироты `X-57` (гасить больше некого) и файлы лога на счёт. Цена: краха процесса больше никто не переживает — упавший коллектор поднимает Планировщик задач, а не менеджер, и до его перезапуска не синхронизируется ничего. Взамен исчез весь класс отказов «процесс счёта умер, а менеджер об этом соврал».

### 8.3 Известные ограничения

- Только Windows. На macOS/Linux коллектор не запускается — сообщение при старте.
- **Синхронизируется тот счёт, который открыт в терминале, и только он.** Остальные ждут. Второй терминал на той же машине делу не помогает: канал `MetaTrader5` один, и какой из терминалов ответит `initialize()` — не наше решение. Очередь по счетам (открывать их по кругу самим) — возможное будущее, но оно требует управлять чужим терминалом, чего коллектор не делает.
- Терминал должен успеть загрузить историю с сервера брокера: после `initialize` ждать до 30 с, пока `history_deals_get` не перестанет расти между двумя вызовами.
- **Автозапуск — Планировщик заданий, а не служба Windows.** Коллектор — обычный процесс, службой он становится только через стороннюю обёртку. Отсюда же «при входе пользователя в систему», а не «при включении компьютера»: терминал MetaTrader 5 — оконная программа, ей нужен рабочий стол сеанса, и заодно это избавляет от хранения пароля Windows в Планировщике. Практическое следствие для человека: выключил машину на ночь — утром коллектор поднимется после входа в систему, а терминал придётся открыть самому.
- **Планировщик молчалив.** Задача, упавшая с ошибкой, выглядит в его списке так же, как отработавшая: об отказе человек узнаёт из карточки счёта («коллектор не на связи», до пяти минут) или из `logs/run-collector.log`, куда `run-collector.bat --service` перекладывает весь свой вывод. `install-service.ps1 -Status` (двойным кликом — `status-collector.bat`) печатает и то, и другое разом, а коды выхода переводит на русский: 0-3 приходят туда от самого коллектора, и самый частый из них — 2, ошибка в `collector.env`.
- **Жёсткое завершение (`taskkill /F`, «Снять задачу») не доводит коллектор до прощания.** Это `TerminateProcess`: ни обработчика сигнала, ни `atexit`, ни `finally`, — значит канал к терминалу не отпускается штатно и прощальный `state=stopped` не уходит. Сирот при этом не остаётся: процесс один (`X-66` закрыл `X-57` вместе с `multiprocessing`).

---

## 9. Фронтенд

### 9.1 Маршруты

```
/login                    — email → код → вход
/                         — Dashboard (v1: summary + календарь‑мини + открытые позиции + «требует внимания»)
/journal                  — таблица позиций
/journal/:id              — карточка позиции (route‑модал поверх таблицы на десктопе, страница на мобильном)
/calendar                 — месяц
/accounts                 — счета, статусы, добавление
/accounts/:id             — счёт: настройки, sync-runs
/settings                 — таймзона, начало дня, имя
/dev/outbox               — только APP_ENV=local: письма с кодами
```

### 9.2 Глобальный переключатель счетов

- Zustand‑store `accountSelection`: `{mode: 'single'|'multi'|'all_real'|'all', ids: string[]}`, сохраняется в `localStorage`, ключ `td.accountSelection.v1`.
- Компонент в шапке: текущий выбор (метки с цветами), выпадающий список счетов с чекбоксами, пресеты «Все реальные», «Все». Демо‑счета в списке помечены бейджем «демо».
- Все запросы через хук `useAccountIds()` → `account_ids` в query. Изменение выбора инвалидирует запросы `journal`, `calendar`, `analytics`.
- Если у пользователя один счёт — переключатель показывает его без выпадающего списка. Заводить счета из переключателя в этом случае нечем: кнопка живёт в списке, а экран `/accounts` в одном клике по меню.
- Смешивание демо и реала: пока в выборке есть счета обоих видов, переключатель показывает предупреждение‑бейдж «демо и реал вместе».
- Заведение счёта из списка (`S2-11`): та же форма, что на `/accounts`, в модальном окне. **Успех не закрывает окно молча**: человек завёл счёт, стоя на дашборде или в журнале, и под окном нет ничего, что бы ему ответило. Окно называет, что произошло (коллектор возьмёт счёт в работу, сделок до первого синка нет, а первый синк начнётся, когда человек откроет этот счёт в терминале — `T-07`), говорит, вошёл ли новый счёт в текущий выбор, и предлагает открыть его карточку или переключить выбор на него. **Выбор счетов сам не меняется** — это настройка рабочего места.
- ⚠️ **Пресет «Все реальные» показывается, только когда у пользователя есть счета обоих видов** (решено в `S2-11`). Без единого реального счёта он даёт пустую выборку — то есть выглядит поломкой ровно тогда, когда работает как задумано; у первого пользователя все четыре счёта демо, и это его обычное состояние, а не край. Без единого демо-счёта он равен «Все», и две кнопки с одним действием заставляют искать между ними разницу. Исключение — уже выбранный `all_real`: он переживает архивацию последнего реального счёта и приезжает из другой вкладки, и спрятанный пресет оставил бы человека с пустым журналом без способа увидеть, чем тот пуст.
- ⚠️ **Предупреждение считается по фактическому составу выборки, а не по имени пресета** (решено в `S2-11`): смешать демо и реал вручную галочками так же легко, как пресетом «Все», и сумма выходит та же. Обратная сторона важнее: у пользователя с одними демо-счетами пресет «Все» ничего не смешивает, и висящее там постоянно предупреждение за неделю перестало бы читаться.

### 9.3 Экраны

**Login.** Поле email → «Получить код» → поле кода (6 цифр, автосабмит) → редирект на `/`. Ошибки 429 — с таймером. Ссылка «Открыть письма (dev)» при `APP_ENV=local`.

**Accounts.** Карточки счетов: цветная полоса, метка, демо‑бейдж, брокер/сервер/логин, статус (`connected` зелёный с «синк 1 мин назад», `pending` серый «ожидает коллектор», `needs_attention` красный с `status_message`, `paused`), кнопки «Синхронизировать», «Пауза», меню «Изменить / Архивировать / Удалить». Форма добавления — модал: платформа (MT5 / Вручную), метка, демо, цвет (палитра), для MT5 — сервер и логин. **Поля пароля в форме нет** (`T-07`, ADR‑0006), и вместо подсказки про инвесторский пароль у логина стоит строка о том, чем коллектор попадёт в счёт: он подключается к терминалу, открытому человеком, а логин нужен, чтобы узнать этот счёт среди открытых. Блок «Коллектор»: `last_heartbeat_at`, инструкция‑ссылка на `SETUP.md` и **правило с его ценой словами** — синхронизируется тот счёт, который открыт в терминале; остальные ждут своей очереди, и пропущенное догоняется окном от последней синхронизации. У счёта в статусе `pending` то же следствие стоит на его карточке («синк начнётся, когда коллектор выйдет на связь и этот счёт будет открыт в MetaTrader 5»); у счёта «вручную» — не стоит, коллектор его не забирает. **Порог «не на связи» на фронте не дублируется** (решение `S1-11`): в списке показывается факт со временем («выходил на связь 10 минут назад»), без вердикта; вердикт приходит с сервера полем `collector_online` в ответе `POST /accounts/{id}/sync-now`. Жёлтое предупреждение в списке — только при `last_heartbeat_at = null`: это другое утверждение, «связи не было ни разу», и оно не требует порога. Причина: число 5 минут уже живёт на сервере в одном месте на трёх потребителей (`is_collector_online`, `check_collectors`, экран счетов), и четвёртая копия разошлась бы с ними молча. Штатный признак «замолчал» — статус `needs_attention`, который ставит `check_collectors`.

**Journal.** Панель фильтров (период с пресетами: сегодня, неделя, месяц, всё; **состояние: открытые / закрытые**; символ; направление; результат; теги; «без рефлексии»; поиск). Фильтр состояния добавлен в `S2-06`: `status` есть у эндпоинта 5.4, а открытая позиция отличается от закрытой не значением поля, а тем, что у неё нет `close_time` — без отдельного фильтра её не отобрать. Таблица (виртуализированная): цвет счёта | дата закрытия | символ | направление | объём | вход → выход | длительность | net P&L (цвет) | R (если есть) | теги | иконки: рефлексия заполнена / скриншот. Клик — карточка. Сверху — summary за фильтр (`/analytics/summary`). Фильтры — в URL query. Мобильный (< 768px): список карточек с теми же данными в 2 строки.

**Position card.** Шапка: символ, направление, счёт, статус, net P&L крупно, gross/commission/swap мелко. Блок «Сделки брокера» — таблица deals (только чтение). Блок «План» — planned entry/SL/TP, risk_amount → расчёт R (`net_pnl / risk_amount`; если `risk_amount` нет, но есть `planned_sl` и symbol в словаре — `|avg_entry − planned_sl| × volume × contract_size` для fx/metal, иначе «н/д»). Блок «Заметки и теги». Блок «Рефлексия» — форма: два ряда кнопок‑оценок A/B/C/D, переключатель «по плану», три селекта эмоций с иконками, чипы ошибок (мультивыбор), уверенность 1–5, текст; автосохранение с задержкой 800 мс, индикатор «сохранено». Блок «Скриншоты» — drag‑and‑drop, вставка из буфера (`paste`), клиентское сжатие до 2000px/85% (canvas), превью, лайтбокс, удаление. Навигация «← предыдущая / следующая →» по текущему списку.

**Calendar.** Сетка месяца; в ячейке net P&L (цвет), число сделок; при нескольких счетах — при наведении разбивка по счетам. ⚠️ **Там, где наведения нет, у разбивки обязан быть эквивалент по нажатию** (решено в `S2-09`): на телефоне это строка дня с открытой разбивкой, на сенсорном планшете — кнопка раскрытия у ячейки. Наведение — способ, а не требование; требование в том, что число дня складывается из счетов, и человек должен видеть, из каких. Признак — медиазапрос на указатель, а не ширина: планшет шириной 1024 px наводить не умеет. Клик по дню — журнал с фильтром на день. Итоги по неделям справа, по месяцу сверху. Переключение месяцев, «сегодня».

**Dashboard (v1).** Summary за 30 дней; календарь‑мини текущего месяца; список открытых позиций с текущим `profit` из последнего `open_positions`; блок «Требует внимания»: счета `needs_attention`, коллектор не на связи, N сделок без рефлексии (ссылка на журнал с фильтром), пустое состояние с шагами онбординга (добавить счёт → запустить коллектор → дождаться синка → заполнить первую рефлексию) с галочками.

**Settings.** Таймзона (список IANA с поиском, по умолчанию из браузера), час начала дня, имя, кнопка «Экспорт всех данных» (этап «Первый тест», JSON‑архив), выход.

**Состояния связи — общие для всех экранов** (решено в `X-42` вместе с `X-13`). Положений дел три, а не два: **«грузится»** — запрос идёт; **«ожидание»** — повтор приостановлен, пока вкладка в фоне, и сам он не сдвинется; **«не отвечает»** — приложение не поднято. Раньше все три выглядели одинаково («Загрузка…»), и два последних читались как зависший экран.

⚠️ **«Ожидание» сегодня достижимо в одном месте — в гейте сессии, и это не недоделка.** Пауза бывает только у **повтора**: старт запроса `networkMode: 'always'` не задерживает, а повтор ждёт фокуса вкладки. Повтор настроен ровно у одного запроса — проверки сессии (`auth/session.ts`, `retry: 1`), потому что ей надо отделить «не смогли спросить» от настоящего выхода из системы; у остальных повторов нет, и в паузу они не попадают. Общее место, которое называет ожидание словами, на экранах со списками всё равно стоит: решение про три состояния принято один раз на приложение, и запрос, которому завтра добавят повторы, не должен снова показать «Загрузка…» без конца.

- Запросы и мутации уходят **всегда** (`networkMode: 'always'` в дефолтах клиента), в том числе когда браузер считает себя офлайн. Причина в том, что установка self-hosted: API живёт на этой же машине, «браузер офлайн» (выключенный Wi-Fi, проснувшийся ноутбук, VPN) о его доступности не говорит ничего, а куда более частый случай обратный — сеть браузер считает живой, а `api` ещё поднимается вместе с Docker Desktop. Поэтому отказ **виден сразу** и у него есть «Повторить», вместо паузы, неотличимой от загрузки.
- Общий `refetchOnWindowFocus` остаётся выключенным, но **упавший** запрос перезапрашивается при возврате во вкладку (у проверки сессии свой `refetchOnWindowFocus`, с `S0-07`: она перезапрашивается и удачной, но лишь протухнув — `staleTime` 30 с): иначе ошибка залипает до F5 даже после того, как `api` доехал, — а человек, дождавшийся Docker Desktop, возвращается во вкладку именно за этим.
- Недоступное API **не уводит с защищённого экрана на `/login`**: форма входа ходит по тому же адресу, то есть это был тупик. Экран остаётся на месте и объясняет, что приложение поднимается вместе с Docker Desktop; «Повторить» возвращает человека туда, куда он шёл.
- «Приложение не поднято» отличается от «API сломался внутри» по ответу: ответа не пришло вовсе либо на 5xx нет тела §5.1 (так отвечает **прокси перед `api`**, пока контейнер `api` стартует: в профиле `local` это dev-сервер vite, в `prod` — Caddy). `internal_error` с телом — живой сервер, и звать там проверять Docker Desktop было бы неправдой.
- У чтений есть общий предел ожидания (30 с): соединение, которое приняли и не ответили, иначе не падает вовсе. Оборванное так чтение гейт сессии считает тем же «не отвечает»: у чтения нет побочных эффектов, и молчавшее полминуты соединение от мёртвого человеку ничем не отличается. ⚠️ На экранах со списками тот же обрыв объясняется иначе — «не ответил вовремя»: там текст выбирает `messageForError`, и он проверяет предел раньше. Расхождение осознанное и существовало до `X-42`. **У записи общего предела нет** — оборванная мутация неотличима от применённой; где предел записи нужен, его ставит вызывающий со своим текстом («запрос мог и дойти»; карточка позиции, 15 с).

### 9.4 Форматирование

- Деньги: `-1 234,56 $` (ru‑RU, знак перед числом, USD), зелёный/красный/серый.
- Даты: `02.09.2026 17:03` в tz пользователя; относительные («2 мин назад») для статусов.
- Цены: по `symbols.digits`, иначе 5 знаков.

---

## 10. Фоновые задачи (arq)

| Задача | Триггер | Действие |
|---|---|---|
| `refresh_daily_stats(account_id, days \| within)` | после ингеста, после ручной сделки/правки | Пересчёт затронутых дней в `daily_stats` (таблица, не MV — обновление точечное). Сузить можно списком дней или отрезком `time_utc` (`within`, см. 5.3 п. 6); без сужения пересчитываются все дни счёта |
| `send_email(to, template, ctx)` | auth | Через `EmailProvider`, 3 ретрая |
| `cleanup_otp()` | cron каждые 10 мин | Удаление просроченных кодов |
| `check_collectors()` | cron каждую минуту | Счета с `last_heartbeat_at` старше 5 мин и статусом `connected` → `needs_attention`, `status_message="Коллектор не на связи"` |
| `export_user_data(user_id)` | Settings | JSON‑архив всех таблиц пользователя в S3, ссылка на скачивание |

---

## 11. Инфраструктура и запуск

### 11.1 `docker-compose.yml`

Сервисы: `postgres` (16, volume `td_pgdata`), `redis`, `api` (`uvicorn`, `alembic upgrade head` при старте), `worker`, `web`. Профиль `local` добавляет `minio` (S3) и `web` в dev‑режиме (Vite с hot reload на 5173, прокси `/api` → `api:8000`). Профиль `prod` добавляет `caddy` (домен из `.env`, автосертификат) и собирает `web` в статический nginx‑образ.

### 11.2 `.env.example`

```
APP_ENV=local                 # local | prod
APP_NAME=TradeDesk
APP_URL=http://localhost:5173
SECRET_KEY=…                  # сессии, подпись
MASTER_KEY=…                  # base64 32 байта, шифрование credentials. ПОТЕРЯ НЕОБРАТИМА
MASTER_KEY_PREVIOUS=          # только на время ротации, см. docs/adr/0003
OTP_PEPPER=…
COLLECTOR_TOKEN=…
DATABASE_URL=postgresql+asyncpg://td:td@postgres:5432/td
REDIS_URL=redis://redis:6379/0
EMAIL_PROVIDER=console        # console | resend
RESEND_API_KEY=
EMAIL_FROM=TradeDesk <no-reply@example.com>
S3_ENDPOINT=http://minio:9000
S3_BUCKET=td
S3_ACCESS_KEY=… S3_SECRET_KEY=…
SENTRY_DSN=
TRUSTED_PROXIES=              # ТОЛЬКО точные адреса прокси через запятую, не подсети
POSTGRES_PASSWORD=            # генерируется `make init`
DOMAIN=                       # только профиль prod
```

Список инфраструктурных переменных вырос в S0-06: `TRUSTED_PROXIES` (иначе лимит по IP становится общим на всю установку — см. `docs/tickets/X-06.md`), `POSTGRES_PASSWORD` (дефолтного `td:td` в проде быть не должно), `DOMAIN` для профиля `prod` и закомментированные `*_PORT` для случая занятых портов.

⚠️ `TRUSTED_PROXIES` принимает **только точные адреса**. Подсеть включает шлюз docker, а значит доверять ей — то же, что доверять любому запросу с хоста: проверено прогоном, подделанные адреса проходят целиком.

`make init` генерирует секреты в `.env` из `.env.example`, если файла нет.

### 11.3 Скрипты (`infra/scripts`)

- `start.bat|sh` — `docker compose --profile local up -d`, вывод URL и подсказки про `/dev/outbox`.
- `stop.bat|sh`.
- `update.bat|sh` — `backup` → скачивание и распаковка zip релиза **поверх текущей установки** (с сохранением `.env` и `backups/`) → `docker compose build` → `up -d` (миграции применяет `api` при старте) → вывод версии. Отказывается работать, если `.env` не найден или `MASTER_KEY` не совпадает с тем, которым зашифрованы данные в томе: иначе распаковка в новую папку молча создала бы новый ключ и сделала пароли счетов нечитаемыми (ADR-0005).
- `backup.bat|sh` — `pg_dump` в `backups/td-<date>.sql.gz`, хранить последние 14.
- `restore.bat|sh <file>`.
- `*.bat` — обёртки без логики: находят `bash.exe` из Git for Windows (общий `find-bash.bat`) и зовут свой `.sh` **по полному пути**. `where bash` не используется даже как запасной вариант: установщик Git по умолчанию кладёт в `PATH` только `Git\cmd`, а после установки WSL2 `where` находит `C:\Windows\System32\bash.exe` — запускалку подсистемы, а не оболочку; системный `PATH` просматривается раньше пользовательского, поэтому правкой `PATH` это не лечится (`X-63`). Ищутся `%ProgramFiles%\Git\bin`, `%ProgramFiles(x86)%\Git\bin`, `%LOCALAPPDATA%\Programs\Git\bin` и папка, выведенная из `git.exe` в `PATH`; переопределение — `TD_BASH`. Отказ называет места, где искал. `find-bash.bat` — единственный из семи, кто печатает русский текст сам, из `cmd`, поэтому он написан по рецепту `apps/collector-mt5/*.bat` (`S1-10`): UTF-8 **без BOM**, переводы строк **CRLF**, `chcp 65001` **первой командой**. Остальные шесть своего текста не печатают — весь их вывод идёт через `bash`.
- Вывод скриптов называет команды **той платформы, на которой они выполняются**: `make …` на macOS и Linux, `infra\scripts\*.bat` на Windows (`td_cmd` в `common.sh`). Совет выполнить несуществующую команду человек читает в момент действия, а не после (`X-64`).

### 11.4 Миграции

Только вперёд‑совместимые: новые колонки — nullable или с default; переименования — через добавление + backfill + удаление в следующем релизе. Перед PR с миграцией — прогон `alembic upgrade head` на дампе тестовых данных в CI.

---

## 12. Задачи по этапам (для постановки агентам)

Формат: `ID — название — Definition of Done`. Порядок внутри этапа — рекомендуемый; зависимости указаны.

### Этап 0 — Фундамент

- **S0‑01 Скелет монорепо** — структура 2.1, `Makefile`, `ruff/mypy/eslint/prettier`, pre‑commit, GitHub Actions (lint + test api, lint + build web). DoD: CI зелёный на пустых приложениях.
- **S0‑02 API‑скелет** — `main.py`, config через pydantic‑settings, async‑SQLAlchemy, Alembic, `GET /health`, structlog JSON‑логи, Sentry по DSN, обработчик ошибок 5.1. DoD: `/health` отдаёт статусы БД и Redis; guard тестовой БД — имя обязано содержать `_test`, исключение бросается до первого запроса (раздел 13).
- **S0‑03 Миграция ядра** — все таблицы раздела 3 (кроме `daily_stats` — S3‑xx). DoD: `alembic upgrade head` / `downgrade base` без ошибок; ER‑диаграмма в `docs/`.
- **S0‑04 Auth** — раздел 4 полностью, `ConsoleEmailProvider`, `dev_outbox`, rate‑limit. DoD: интеграционные тесты: запрос кода, неверный код ×5 → блок, верный код → cookie, `me`, logout, 429.
- **S0‑05 Шифрование credentials** — `core/security.py`: envelope‑схема 3.2, функции `encrypt_credentials(dict) -> (ciphertext, wrapped_key)`, `decrypt_credentials`, ротация `MASTER_KEY` (скрипт). DoD: тесты, включая ротацию.
- **S0‑06 Docker Compose local/prod** — 11.1–11.3, `make init`. DoD: на чистой машине `make init && make up` → login работает, код виден в `/dev/outbox`.
- **S0‑07 Web‑скелет** — Vite, роутер 9.1 с заглушками, layout (сайдбар, шапка с местом под переключатель), тёмная тема (по умолчанию) + светлая, `openapi-typescript` генерация (`make types`), клиент с обработкой 401 → редирект на `/login`, страница Login, `/dev/outbox`. DoD: вход через UI по коду из outbox.
- **S0‑08 Settings** — `GET/PATCH /users/me` (timezone, day_boundary_hour, display_name), экран Settings. DoD: смена tz меняет отображение времени в UI.
- **S0‑09 SETUP.md черновик** — установка Docker Desktop, клонирование, `make init`, `start`, вход. DoD: сосед по проекту прошёл по нему без вопросов.

### Этап 1 — Коллектор MT5 и ингест

- **S1‑01 JSON Schema ингеста** — `ingest-deals.schema.json`, валидация в API (pydantic‑модели генерируются/сверяются со схемой в тесте). DoD: невалидный батч → 400 с указанием поля.
- **S1‑02 Нормализатор deals** — раздел 6.2–6.3, `normalizer.py`, чистые функции. DoD: unit‑тесты на все маппинги, на смещение времени, на `other` с `position_id`.
- **S1‑03 Сборщик позиций** — раздел 7, фикстуры `docs/fixtures.md`. DoD: 8 фикстур проходят; свойство идемпотентности проверено тестом (двойной прогон = тот же результат); тест «два батча с перекрытием».
- **S1‑04 `POST /ingest/deals`** — 5.3 целиком, транзакция, `sync_runs`, постановка `refresh_daily_stats`. DoD: интеграционный тест с Postgres: 2 батча с перекрытием → без дублей, позиции верны; 5 001 deal → 413.
- **S1‑05 `POST /ingest/heartbeat` + `GET /internal/collector/assignments`** — 5.3, 5.6, `check_collectors` cron. DoD: тесты статусных переходов `pending → connected → needs_attention`.
- **S1‑06 Accounts API** — 5.2. DoD: тесты CRUD, архивирование удаляет credentials, удаление каскадно чистит deals/positions; не‑USD валюта в `account_info` → `needs_attention` с сообщением.
- **S1‑07 Символы** — 6.4, seed‑словарь, эвристика. DoD: тесты на 30 примеров суффиксов.
- **S1‑08 Коллектор: mt5_client + worker** — 8.2 для одного счёта, ручной запуск с `--account-id`. DoD: на реальном демо‑счёте история загружается в локальный API; закрытие сделки в терминале → в базе через ≤ 90 с; перезапуск процесса не создаёт дублей.
- **S1‑09 Коллектор: менеджер процессов, heartbeat, assignments** — `main.py`, лимит, остановка при паузе. DoD: два счёта одновременно; пауза одного останавливает его процесс. ⚠️ **Отменено в `X-66`/`T-07`:** пула процессов больше нет, канал `MetaTrader5` один на машину, и одновременно синхронизируется один счёт — тот, что открыт в терминале (§8.2). DoD этой задачи в исходном виде невыполним, требование про `MAX_ACCOUNTS` и лимит счетов снято вместе с самим лимитом. В силе осталось то, ради чего оно было написано: **счёт, который не синхронизируется, обязан быть виден человеку, а не съеден молча.** Четыре счёта первого пользователя работают все, но по очереди — по одному за раз, и очередь задаёт он сам, входя в счёт в терминале.
- **S1‑10 Коллектор: установка** — `run-collector.bat`, `install-service.ps1`, читаемые ошибки MT5. DoD: после перезагрузки Windows коллектор поднялся сам; неверный пароль виден в UI как «Неверный пароль инвестора». ⚠️ **Вторая половина DoD отменена в `T-07`:** пароля у счёта больше нет, коллектор в терминал не входит. Её место занял сценарий «терминал открыт на чужом счёте»: синхронизации нет, и на карточке видно, какой счёт открыт (§8.2, пункт 4). ⚠️ **Версия Python называется явно.** Пакет требует `>=3.12`, но гейт гоняет только 3.12, то есть на любой другой коллектор поедет на версии, которую не проверял никто. Человек же поставит то, что предлагает python.org первой кнопкой (сейчас 3.14). Либо инструкция называет версию и `run-collector.bat` её проверяет, либо гейт начинает гонять ту, которую человек поставит. Молчать нельзя — это машина, до которой мы не дотянемся.
- **S1‑11 UI Accounts** — 9.3 Accounts, переключатель счетов 9.2 (пока используется только здесь). DoD: добавил счёт → через минуту статус `connected` и число позиций > 0.
- **S1‑12 Сверка** — скрипт `scripts/reconcile.py`: сравнение суммы `net_pnl` закрытых позиций и `Σ profit+commission+swap` по deals счёта с отчётом терминала за период. DoD: расхождение 0,00 на трёх счетах (два своих + демо).

### Этап 2 — Журнал

- **S2‑01 Journal API: список и карточка** — 5.4 `GET` эндпоинты, фильтры, курсор, сортировки, `result`. DoD: тесты фильтров и пагинации; `account_ids` чужого пользователя → 404.
- **S2‑02 Journal API: entry, reflection, tags, vocab** — DoD: тесты; `filled_at` логика; теги нормализуются (trim, регистр сохраняется, уникальность без учёта регистра).
- **S2‑03 Ручные сделки** — 5.4 manual, синтетический deal, запрет правки импортированных. DoD: тесты; ручная сделка попадает в календарь и summary.
- **S2‑04 Вложения** — presign/confirm/delete, S3 (minio локально), лимиты, presigned GET. DoD: тесты через minio в testcontainers.
- **S2‑05 Календарь API + `analytics/summary`** — `daily_stats` таблица, `refresh_daily_stats`, `docs/metrics.md` с формулами summary. DoD: тесты формул на ручных примерах; день по tz и `day_boundary_hour`.
- **S2‑06 UI Journal таблица** — 9.3 Journal, виртуализация, фильтры в URL, summary‑шапка, мобильные карточки. DoD: 5 000 позиций скроллятся без лагов; фильтр восстанавливается из URL после перезагрузки.
- **S2‑07 UI Position card** — все блоки 9.3, автосохранение, навигация prev/next. DoD: рефлексия заполняется за ≤ 30 с (замер вручную); потеря сети при сохранении показывает ошибку и не теряет ввод.
- **S2‑08 UI Скриншоты** — drag‑and‑drop, paste, сжатие, лайтбокс. DoD: 10 МБ PNG сжимается и грузится ≤ 3 с локально.
- **S2‑09 UI Calendar** — 9.3. DoD: суммы дней совпадают с журналом за тот же день; разбивка по счетам при наведении. ⚠️ Границы дня **берутся из ответа календаря** (`starts_at`/`ends_at`), а не вычисляются заново, и клик по дню открывает журнал с ними **и с `status=closed`**: без последнего в список приедут ещё и позиции, открытые в этом окне, и сумма разойдётся с днём (`S2-05`, `docs/metrics.md` §5).
- **S2‑10 UI Dashboard v1** — 9.3 Dashboard, пустое состояние с онбордингом. DoD: новый пользователь видит шаги; после подключения счёта галочки проставляются. ⚠️ Сводка считает только закрытые позиции (5.5), поэтому при `open_positions > 0` экран **обязан показать их число и объяснить разницу**; при нуле сумма колонки журнала обязана сходиться с шапкой до копейки. Иначе человек с калькулятором приходит с багом, которого нет, — и расхождение по умолчанию возникает при первой же открытой сделке, а не при ошибке.
- **S2‑11 Полировка переключателя счетов** — применён ко всем экранам, пресеты, предупреждение «демо + реал». DoD: смена выбора обновляет журнал, календарь, дашборд без перезагрузки.

### Веха «Первый тест»

- **T‑01 SETUP.md финальный** — для не‑разработчика на Windows: Docker Desktop + WSL2, скачивание zip со страницы релизов (**не клонирование** — дистрибуция архивом, `v1.7` и ADR‑0005; Git на машине не нужен), `start.bat`, вход, установка Python и коллектора, `collector.env`, `install-service.ps1`, проверка статуса; скриншоты; раздел «Если что‑то не так» (коллектор не на связи, терминал не открыт или открыт на чужом счёте, счёт не в USD, Docker не стартует, порт занят). DoD: прогон на чистой Windows‑VM по инструкции без подсказок. ⚠️ **Переписан по итогам первого прогона — `T‑08`**: прогон 10 сентября 2026 дошёл до коллектора и встал на нём, после чего механизм коллектора переделан (ADR‑0006), и вся глава про коллектор в `SETUP.md` описывает **открытый человеком терминал**, а не вход паролем; §1 получил измеренную последовательность включения WSL2 (`X‑65`), включая два шага, которым нужна сеть. ⚠️ **Скриншотов по‑прежнему нет:** снимать их надо на Windows, а с того прогона снимков не делали. Полный список того, что в `SETUP.md` не проверено, — в самом документе, раздел «Что здесь проверено, а что нет».
- **T‑02 Скрипты `update/backup/restore`** — 11.3. DoD: `update` на базе с данными не теряет позиции и рефлексии; `restore` из бэкапа восстанавливает всё.
- **T‑03 Экспорт/импорт данных пользователя** — `export_user_data` + `scripts/import_user_data.py` (импорт в другую инсталляцию с новым `user_id`, сохранение связей). DoD: экспорт на ноутбуке → импорт на сервере → журнал идентичен (сравнение счётчиков и контрольных сумм).
- **T‑04 Кнопка «Сообщить о проблеме»** — копирует в буфер: версия, ОС/браузер, выбранные счета, последние 20 строк ошибок коллектора (через `sync_runs.error`), user_id. DoD: текст вставляется в Telegram и читаем.
- **T‑05 Чек‑лист приёмки** — `docs/acceptance-first-test.md` по PLAN.md (веха «Первый тест», п. 7). DoD: заполнен нами на своих данных до передачи другу.
- **T‑06 Тест инструкции на чистой машине** — DoD: видео/заметки прогона, все затыки исправлены в `SETUP.md`.

---

## 13. Тестирование и качество

- `make test` — unit + интеграционные (Postgres и minio через testcontainers). Порог покрытия для `ingest` и `analytics` — 90 %.
- Фикстуры deals — обезличенные реальные выгрузки (`login` заменён, `comment` очищен), формат — JSON батча из 5.3.
- Smoke‑тесты Playwright: вход, добавление ручной сделки, заполнение рефлексии, календарь показывает день. Запускаются в CI против `docker compose --profile local`.
- Нагрузочная проверка (этап 2): скрипт `scripts/seed_synthetic.py` — 3 счёта × 5 000 позиций; журнал и календарь отвечают ≤ 300 мс на p95 локально.

---

## 14. Открытые вопросы и значения по умолчанию

| Вопрос | Значение по умолчанию (используем, пока не решено иначе) |
|---|---|
| Название продукта | TradeDesk (`APP_NAME`) |
| Таймзона по умолчанию | `Asia/Yekaterinburg` для первых пользователей; в UI берётся из браузера при первом входе |
| Начало торгового дня | 00:00 tz пользователя (`day_boundary_hour=0`) |
| Палитра счетов | 8 цветов Tailwind‑500: emerald, sky, amber, violet, rose, teal, orange, indigo |
| Расчёт R без `risk_amount` | Только fx/metal по словарю символов; иначе «н/д» |
| Максимум счетов на пользователя | Не ограничен в API; коллектор синхронизирует по одному — тот счёт, который открыт в терминале (§8.2) |
| Хранение скриншотов | S3 (minio локально), путь `users/<user_id>/positions/<position_id>/<uuid>.<ext>` |
| Retention `sync_runs` | 90 дней, cron‑очистка |
| Язык UI | Только русский в v1 |
| Демо + реал в сводке | Разрешено через пресет «Все» с предупреждением |
