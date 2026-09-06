export interface paths {
  '/api/v1/health': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Health */
    get: operations['health_api_v1_health_get'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/version': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Get Version */
    get: operations['get_version_api_v1_version_get'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/auth/request-code': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Request Code */
    post: operations['request_code_api_v1_auth_request_code_post'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/auth/verify': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Verify */
    post: operations['verify_api_v1_auth_verify_post'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/auth/logout': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /**
     * Logout
     * @description Идемпотентен: без cookie и с чужим идентификатором ответ тот же 204.
     */
    post: operations['logout_api_v1_auth_logout_post'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/auth/me': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Me */
    get: operations['me_api_v1_auth_me_get'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/users/me': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Read Me */
    get: operations['read_me_api_v1_users_me_get'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    /**
     * Update Me
     * @description Меняет только владельца сессии: чужой идентификатор передать некуда.
     *
     *     Без сессии тело не разбирается pydantic и состав полей наружу не уходит. Сам JSON
     *     при этом FastAPI читает раньше зависимостей, поэтому синтаксически битое тело даёт
     *     400 и без cookie — по нему видно только то, что запрос не JSON.
     */
    patch: operations['update_me_api_v1_users_me_patch'];
    trace?: never;
  };
  '/api/v1/users/timezones': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /**
     * List Timezones
     * @description Имена зон, которые принимает `PATCH /users/me`, — из того же набора.
     *
     *     Под сессией, как и весь `/users`: анонимного потребителя у списка нет, а открытый
     *     маршрут — это девять килобайт на неаутентифицированный запрос без лимита.
     */
    get: operations['list_timezones_api_v1_users_timezones_get'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/accounts': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /**
     * List Accounts
     * @description Счета пользователя со счётчиком позиций.
     *
     *     Архивные по умолчанию скрыты: переключатель счетов (SPEC.md 9.2) показывает только
     *     живые. Экрану «Счета» они нужны — иначе архив исчезает без следа, — поэтому у списка
     *     есть флаг, а не два разных маршрута.
     */
    get: operations['list_accounts_api_v1_accounts_get'];
    put?: never;
    /**
     * Create Account
     * @description Создаёт счёт в статусе `pending`. Пароль сразу шифруется и в ответ не попадает.
     */
    post: operations['create_account_api_v1_accounts_post'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/accounts/{account_id}': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    post?: never;
    /**
     * Delete Account
     * @description Удаляет счёт со всеми сделками, позициями и записями журнала на них.
     *
     *     Необратимо; на фронте подтверждается вводом имени счёта (SPEC.md 5.2). Что именно
     *     теряется — в docstring `service.delete_account`.
     */
    delete: operations['delete_account_api_v1_accounts__account_id__delete'];
    options?: never;
    head?: never;
    /**
     * Update Account
     * @description Частичная правка. Смена пароля или пары сервер+логин возвращает счёт в `pending`.
     */
    patch: operations['update_account_api_v1_accounts__account_id__patch'];
    trace?: never;
  };
  '/api/v1/accounts/{account_id}/pause': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Pause Account */
    post: operations['pause_account_api_v1_accounts__account_id__pause_post'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/accounts/{account_id}/resume': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Resume Account */
    post: operations['resume_account_api_v1_accounts__account_id__resume_post'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/accounts/{account_id}/archive': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /**
     * Archive Account
     * @description Выводит счёт из работы и удаляет его credentials. Сделки остаются.
     */
    post: operations['archive_account_api_v1_accounts__account_id__archive_post'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/accounts/{account_id}/sync-now': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /**
     * Sync Now
     * @description Просит внеочередной синк. `202`, а не `200`: сделки заберёт коллектор, а не этот
     *     запрос — SPEC.md 8.2, он сверяет `sync_requested_at` с последним синком на очередном
     *     heartbeat. `collector_online` возвращается затем, чтобы UI отличал «попросили, сейчас
     *     сделает» от «попросили, но коллектор не запущен».
     */
    post: operations['sync_now_api_v1_accounts__account_id__sync_now_post'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/accounts/{account_id}/sync-runs': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /**
     * List Sync Runs
     * @description Последние 50 прогонов синка, новые сверху.
     */
    get: operations['list_sync_runs_api_v1_accounts__account_id__sync_runs_get'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/journal/positions': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /**
     * List Positions
     * @description Страница журнала.
     *
     *     Сортировка по умолчанию — `close_time:desc`: журнал открывают, чтобы увидеть, чем
     *     кончился сегодняшний день. Открытые позиции при сортировке по времени закрытия и по
     *     длительности идут первой группой в обе стороны — у них этих значений нет, а прятать
     *     их в хвост тысячестрочного списка нельзя.
     */
    get: operations['list_positions_api_v1_journal_positions_get'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/journal/positions/{position_id}': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /**
     * Get Position
     * @description Карточка позиции со сделками, записью журнала и рефлексией.
     */
    get: operations['get_position_api_v1_journal_positions__position_id__get'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/ingest/heartbeat': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /**
     * Heartbeat
     * @description Коллектор сообщает, что жив и что происходит с каждым его счётом.
     *
     *     Ответ — счётчики, а не ошибка: heartbeat про десять счетов не должен падать целиком
     *     из-за одного идентификатора, который коллектор запомнил до архивации счёта.
     */
    post: operations['heartbeat_api_v1_ingest_heartbeat_post'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/internal/collector/assignments': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /**
     * Assignments
     * @description За какими счетами следить и чем в них входить. **Единственный ответ с паролем.**
     *
     *     Форма ответа — конверт `{items}`, как у `GET /accounts`. Голый массив нечем расширить,
     *     а курсорная пагинация из SPEC.md 5.1 потребовала бы ломающей правки вместо добавления
     *     поля; потребитель (`S1-08`) ещё не написан, поэтому смена формы сейчас стоит ноль.
     *     SPEC.md 5.6 обновлена тем же диффом.
     *
     *     `GET`, который пишет: выдача закрепляет `collector_id` за счётом (§5.6). Без этого
     *     два коллектора в одной сети получили бы одни и те же счета и полезли бы в один
     *     брокерский аккаунт двумя терминалами.
     */
    get: operations['assignments_api_v1_internal_collector_assignments_get'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/api/v1/dev/outbox': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** List Outbox */
    get: operations['list_outbox_api_v1_dev_outbox_get'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
}
export type webhooks = Record<string, never>;
export interface components {
  schemas: {
    /**
     * AccountBrief
     * @description Счёт в строке журнала — SPEC.md 5.4: «account {id,label,color,is_demo}».
     */
    AccountBrief: {
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /** Label */
      label: string;
      /** Color */
      color: string;
      /** Is Demo */
      is_demo: boolean;
    };
    /**
     * AccountCreateRequest
     * @description Тело `POST /accounts` (SPEC.md 5.2).
     */
    AccountCreateRequest: {
      /**
       * Label
       * @description Название счёта, например «Демо FTMO»
       */
      label: string;
      /**
       * Platform
       * @description Источник сделок
       * @enum {string}
       */
      platform: 'mt5' | 'csv' | 'manual';
      /**
       * Is Demo
       * @description Демо-счёт
       * @default false
       */
      is_demo: boolean;
      /**
       * Color
       * @description Цвет из палитры. Если не задан — назначается первый свободный
       */
      color?:
        | (
            | '#2563eb'
            | '#16a34a'
            | '#dc2626'
            | '#d97706'
            | '#7c3aed'
            | '#0891b2'
            | '#db2777'
            | '#65a30d'
          )
        | null;
      /**
       * Broker
       * @description Брокер, свободный текст
       */
      broker?: string | null;
      /**
       * Server
       * @description Сервер MT5, например FTMO-Demo
       */
      server?: string | null;
      /**
       * Login
       * @description Номер счёта MT5
       */
      login?: number | null;
      /** Password */
      password?: string | null;
      /**
       * Sort Order
       * @description Порядок в переключателе счетов
       * @default 0
       */
      sort_order: number;
    };
    /**
     * AccountResponse
     * @description Карточка счёта. Ровно эти поля и никаких других — см. docstring модуля.
     */
    AccountResponse: {
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /** Label */
      label: string;
      /** Is Demo */
      is_demo: boolean;
      /** Color */
      color: string;
      /**
       * Platform
       * @enum {string}
       */
      platform: 'mt5' | 'csv' | 'manual';
      /** Broker */
      broker: string | null;
      /** Server */
      server: string | null;
      /** Login */
      login: number | null;
      /** Currency */
      currency: string;
      /** Account Type */
      account_type: ('hedging' | 'netting') | null;
      /** Server Utc Offset Minutes */
      server_utc_offset_minutes: number | null;
      /**
       * Status
       * @enum {string}
       */
      status: 'pending' | 'connected' | 'needs_attention' | 'paused' | 'archived';
      /** Status Message */
      status_message: string | null;
      /** Last Sync At */
      last_sync_at: string | null;
      /** Last Heartbeat At */
      last_heartbeat_at: string | null;
      /** Collector Id */
      collector_id: string | null;
      /** Sort Order */
      sort_order: number;
      /**
       * Created At
       * Format: date-time
       */
      created_at: string;
      /**
       * Positions Count
       * @description Сколько позиций собрано по этому счёту
       */
      positions_count: number;
    };
    /**
     * AccountUpdateRequest
     * @description Тело `PATCH /accounts/{id}` — частичное: отсутствующее поле не трогается.
     *
     *     `broker` — единственное обнуляемое: явный `null` очищает брокера. Остальные поля
     *     обнулить нечем, `null` в них — ошибка валидации, а не «сбрось значение».
     *
     *     ⚠️ Присутствие `password` или **изменение** `server`/`login` сбрасывает статус
     *     (см. `service.update_account`). Форма редактирования отправляет карточку целиком,
     *     поэтому решает не присутствие поля, а разница значений: иначе переименование счёта
     *     останавливало бы работающий синк.
     */
    AccountUpdateRequest: {
      /** Label */
      label?: string;
      /** Is Demo */
      is_demo?: boolean;
      /**
       * Color
       * @enum {string}
       */
      color?:
        | '#2563eb'
        | '#16a34a'
        | '#dc2626'
        | '#d97706'
        | '#7c3aed'
        | '#0891b2'
        | '#db2777'
        | '#65a30d';
      /** Sort Order */
      sort_order?: number;
      /**
       * Broker
       * @description null очищает брокера
       */
      broker?: string | null;
      /** Server */
      server?: string;
      /** Login */
      login?: number;
      /**
       * Password
       * Format: password
       * @description Пароль инвестора. В ответах не возвращается
       */
      password?: string;
    };
    /**
     * AccountsResponse
     * @description Список счетов.
     *
     *     Без курсора, в отличие от общего правила SPEC.md 5.1: счетов у пользователя единицы,
     *     а глобальный переключатель (SPEC.md 9.2) обязан показать все сразу — постраничный
     *     список заставил бы его крутить цикл ради заведомо одной страницы.
     */
    AccountsResponse: {
      /** Items */
      items: components['schemas']['AccountResponse'][];
    };
    /**
     * AssignmentListResponse
     * @description Конверт выдачи — SPEC.md 5.6.
     *
     *     Не голый массив: в него нечего добавить, не сломав потребителя, а курсорная пагинация
     *     из SPEC.md 5.1 однажды потребует именно добавления поля рядом с `items`. Потребитель
     *     (`S1-08`) ещё не написан — момент, когда это стоит ноль. Ту же форму отдаёт
     *     `GET /accounts`.
     */
    AssignmentListResponse: {
      /** Items */
      items: components['schemas']['AssignmentResponse'][];
    };
    /**
     * AssignmentResponse
     * @description Задание коллектору на один счёт — SPEC.md 5.6. **Содержит пароль.**
     */
    AssignmentResponse: {
      /**
       * Account Id
       * Format: uuid
       */
      account_id: string;
      /** Server */
      server: string;
      /** Login */
      login: number;
      /**
       * Password
       * @description Пароль инвестора. Единственный ответ API, где он есть; в пользовательские маршруты не попадает никогда
       */
      password: string;
      /**
       * Sync Requested At
       * @description Просьба пользователя о внеочередном синке (SPEC.md 5.2)
       */
      sync_requested_at: string | null;
      /** Last Sync At */
      last_sync_at: string | null;
      /**
       * Status
       * @enum {string}
       */
      status: 'pending' | 'connected' | 'needs_attention' | 'paused' | 'archived';
    };
    /**
     * DealResponse
     * @description Сделка позиции. `raw` и `time_server` наружу не выходят — это отладка (SPEC.md 3.3).
     */
    DealResponse: {
      /** Deal Ticket */
      deal_ticket: number;
      /** Order Ticket */
      order_ticket: number | null;
      /** Symbol Raw */
      symbol_raw: string;
      /** Deal Type */
      deal_type: string;
      /** Entry */
      entry: string;
      /** Reason */
      reason: string | null;
      /**
       * Volume
       * @description Десятичное число, numeric(18,8)
       */
      volume: string;
      /**
       * Price
       * @description Десятичное число, numeric(18,8)
       */
      price: string;
      /**
       * Profit
       * @description Десятичное число, numeric(18,2)
       */
      profit: string;
      /**
       * Commission
       * @description Десятичное число, numeric(18,2)
       */
      commission: string;
      /**
       * Swap
       * @description Десятичное число, numeric(18,2)
       */
      swap: string;
      /**
       * Fee
       * @description Десятичное число, numeric(18,2)
       */
      fee: string;
      /**
       * Time Utc
       * Format: date-time
       */
      time_utc: string;
      /** Comment */
      comment: string | null;
      /** Magic */
      magic: number | null;
      /** Source */
      source: string;
    };
    /** HealthResponse */
    HealthResponse: {
      /**
       * Status
       * @enum {string}
       */
      status: 'ok' | 'degraded';
      /**
       * Db
       * @enum {string}
       */
      db: 'ok' | 'unavailable';
      /**
       * Redis
       * @enum {string}
       */
      redis: 'ok' | 'unavailable';
      /** Version */
      version: string;
    };
    /**
     * HeartbeatAccount
     * @description Состояние одного счёта в heartbeat.
     */
    HeartbeatAccount: {
      /**
       * Account Id
       * Format: uuid
       */
      account_id: string;
      /**
       * State
       * @description Состояние процесса, следящего за счётом
       * @enum {string}
       */
      state: 'running' | 'error' | 'stopped';
      /**
       * Message
       * @description Причина при state=error. Показывается пользователю, поэтому обязана быть понятным текстом; хранится урезанной до 200 символов
       */
      message?: string | null;
      /**
       * Terminal Login
       * @description Номер счёта, под которым коллектор вошёл в терминал
       */
      terminal_login?: number | null;
    };
    /**
     * HeartbeatRequest
     * @description Тело `POST /ingest/heartbeat` (SPEC.md 5.3).
     */
    HeartbeatRequest: {
      /**
       * Collector Id
       * @description Идентификатор установки коллектора
       */
      collector_id: string;
      /**
       * Accounts
       * @description Пустой список — коллектор жив, но счетов у него нет
       */
      accounts?: components['schemas']['HeartbeatAccount'][];
    };
    /**
     * HeartbeatResponse
     * @description Сколько счетов heartbeat применил и сколько пропустил.
     *
     *     Пропущенные — это чужие, несуществующие и выведенные из работы (`paused`,
     *     `archived`). Счётчик, а не список: коллектор знает, что отправлял, а расхождение
     *     ему нужно только как признак «спроси assignments заново».
     */
    HeartbeatResponse: {
      /** Accepted */
      accepted: number;
      /** Ignored */
      ignored: number;
    };
    /**
     * JournalEntryBrief
     * @description Запись журнала «кратко» (SPEC.md 5.4): теги и одна строка заметки.
     */
    JournalEntryBrief: {
      /** Tags */
      tags: string[];
      /** Has Notes */
      has_notes: boolean;
      /** Notes Preview */
      notes_preview: string | null;
      /** Risk Amount */
      risk_amount: string | null;
      /**
       * Updated At
       * Format: date-time
       */
      updated_at: string;
    };
    /**
     * JournalEntryDetail
     * @description Запись журнала целиком — блок карточки (SPEC.md 9.3).
     */
    JournalEntryDetail: {
      /** Notes */
      notes: string | null;
      /** Tags */
      tags: string[];
      /** Planned Entry */
      planned_entry: string | null;
      /** Planned Sl */
      planned_sl: string | null;
      /** Planned Tp */
      planned_tp: string | null;
      /** Risk Amount */
      risk_amount: string | null;
      /**
       * Updated At
       * Format: date-time
       */
      updated_at: string;
    };
    /** OutboxEntry */
    OutboxEntry: {
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /** To Email */
      to_email: string;
      /** Subject */
      subject: string;
      /** Body Text */
      body_text: string;
      /** Body Html */
      body_html: string | null;
      /**
       * Created At
       * Format: date-time
       */
      created_at: string;
    };
    /**
     * OutboxResponse
     * @description Без курсора: страница показывает последние письма и назад не листает.
     */
    OutboxResponse: {
      /** Items */
      items: components['schemas']['OutboxEntry'][];
    };
    /**
     * PositionCard
     * @description Карточка позиции — SPEC.md 5.4.
     *
     *     ⚠️ Вложений здесь пока нет списком, только счётчик: presigned GET требует S3, а его
     *     в проекте нет до `S2-04`. Поле `attachments` добавит она же.
     */
    PositionCard: {
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /**
       * Position Id
       * @description Идентификатор позиции у брокера
       */
      position_id: number;
      /** Symbol Raw */
      symbol_raw: string;
      /** Symbol Norm */
      symbol_norm: string;
      /**
       * Direction
       * @enum {string}
       */
      direction: 'long' | 'short';
      /**
       * Status
       * @enum {string}
       */
      status: 'open' | 'closed';
      /**
       * Result
       * @description Только у закрытых позиций
       */
      result: ('win' | 'loss' | 'be') | null;
      /**
       * Open Time
       * Format: date-time
       */
      open_time: string;
      /** Close Time */
      close_time: string | null;
      /**
       * Volume Opened
       * @description Десятичное число, numeric(18,8)
       */
      volume_opened: string;
      /**
       * Volume Closed
       * @description Десятичное число, numeric(18,8)
       */
      volume_closed: string;
      /**
       * Avg Entry Price
       * @description Десятичное число, numeric(18,8)
       */
      avg_entry_price: string;
      /** Avg Exit Price */
      avg_exit_price: string | null;
      /**
       * Gross Pnl
       * @description Десятичное число, numeric(18,2)
       */
      gross_pnl: string;
      /**
       * Commission
       * @description Десятичное число, numeric(18,2)
       */
      commission: string;
      /**
       * Swap
       * @description Десятичное число, numeric(18,2)
       */
      swap: string;
      /**
       * Fee
       * @description Десятичное число, numeric(18,2)
       */
      fee: string;
      /**
       * Net Pnl
       * @description Десятичное число, numeric(18,2)
       */
      net_pnl: string;
      /** Deals Count */
      deals_count: number;
      /** Duration Seconds */
      duration_seconds: number | null;
      /** Close Reason */
      close_reason: string | null;
      /** Is Manual */
      is_manual: boolean;
      /**
       * Rebuilt At
       * Format: date-time
       */
      rebuilt_at: string;
      account: components['schemas']['AccountBrief'];
      journal_entry: components['schemas']['JournalEntryDetail'] | null;
      reflection: components['schemas']['ReflectionDetail'] | null;
      /** Attachments Count */
      attachments_count: number;
      /** Deals */
      deals: components['schemas']['DealResponse'][];
    };
    /**
     * PositionListItem
     * @description Строка журнала — SPEC.md 5.4.
     */
    PositionListItem: {
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /**
       * Position Id
       * @description Идентификатор позиции у брокера
       */
      position_id: number;
      /** Symbol Raw */
      symbol_raw: string;
      /** Symbol Norm */
      symbol_norm: string;
      /**
       * Direction
       * @enum {string}
       */
      direction: 'long' | 'short';
      /**
       * Status
       * @enum {string}
       */
      status: 'open' | 'closed';
      /**
       * Result
       * @description Только у закрытых позиций
       */
      result: ('win' | 'loss' | 'be') | null;
      /**
       * Open Time
       * Format: date-time
       */
      open_time: string;
      /** Close Time */
      close_time: string | null;
      /**
       * Volume Opened
       * @description Десятичное число, numeric(18,8)
       */
      volume_opened: string;
      /**
       * Volume Closed
       * @description Десятичное число, numeric(18,8)
       */
      volume_closed: string;
      /**
       * Avg Entry Price
       * @description Десятичное число, numeric(18,8)
       */
      avg_entry_price: string;
      /** Avg Exit Price */
      avg_exit_price: string | null;
      /**
       * Gross Pnl
       * @description Десятичное число, numeric(18,2)
       */
      gross_pnl: string;
      /**
       * Commission
       * @description Десятичное число, numeric(18,2)
       */
      commission: string;
      /**
       * Swap
       * @description Десятичное число, numeric(18,2)
       */
      swap: string;
      /**
       * Fee
       * @description Десятичное число, numeric(18,2)
       */
      fee: string;
      /**
       * Net Pnl
       * @description Десятичное число, numeric(18,2)
       */
      net_pnl: string;
      /** Deals Count */
      deals_count: number;
      /** Duration Seconds */
      duration_seconds: number | null;
      /** Close Reason */
      close_reason: string | null;
      /** Is Manual */
      is_manual: boolean;
      /**
       * Rebuilt At
       * Format: date-time
       */
      rebuilt_at: string;
      account: components['schemas']['AccountBrief'];
      journal_entry: components['schemas']['JournalEntryBrief'] | null;
      reflection: components['schemas']['ReflectionBrief'] | null;
      /** Attachments Count */
      attachments_count: number;
    };
    /**
     * PositionsPage
     * @description Страница списка — конверт SPEC.md 5.1.
     *
     *     Общего числа строк здесь нет намеренно: `count(*)` по журналу стоит столько же, сколько
     *     сама страница, а нужен он одному месту — шапке журнала, которая берёт числа из
     *     `GET /analytics/summary` (S2-05).
     */
    PositionsPage: {
      /** Items */
      items: components['schemas']['PositionListItem'][];
      /**
       * Next Cursor
       * @description Курсор следующей страницы. `null` — страница последняя
       */
      next_cursor: string | null;
    };
    /**
     * ReflectionBrief
     * @description SPEC.md 5.4 обещает в списке ровно `reflection.filled_at` — им и ограничиваемся.
     */
    ReflectionBrief: {
      /** Filled At */
      filled_at: string | null;
    };
    /**
     * ReflectionDetail
     * @description Рефлексия целиком. Значения — из словарей SPEC.md 3.5, их отдаёт `/journal/vocab`.
     */
    ReflectionDetail: {
      /** Setup Grade */
      setup_grade: ('A' | 'B' | 'C' | 'D') | null;
      /** Execution Grade */
      execution_grade: ('A' | 'B' | 'C' | 'D') | null;
      /** Followed Plan */
      followed_plan: boolean | null;
      /** Emotion Before */
      emotion_before: string | null;
      /** Emotion During */
      emotion_during: string | null;
      /** Emotion After */
      emotion_after: string | null;
      /** Mistakes */
      mistakes: string[];
      /** Confidence */
      confidence: number | null;
      /** Free Text */
      free_text: string | null;
      /** Filled At */
      filled_at: string | null;
      /**
       * Updated At
       * Format: date-time
       */
      updated_at: string;
    };
    /** RequestCodeRequest */
    RequestCodeRequest: {
      /** Email */
      email: string;
    };
    /**
     * RequestCodeResponse
     * @description Ответ одинаков для существующего и несуществующего адреса (SPEC.md 4).
     */
    RequestCodeResponse: {
      /**
       * Status
       * @default accepted
       * @constant
       */
      status: 'accepted';
    };
    /**
     * SyncNowResponse
     * @description Ответ `POST /accounts/{id}/sync-now` (SPEC.md 5.2).
     *
     *     Это расписка о принятой просьбе, а не результат синка: выполняет его коллектор на
     *     следующем heartbeat. Поэтому здесь `collector_online` — без него единственное, что
     *     UI мог бы сказать после нажатия «Синхронизировать», это «готово», и на выключенном
     *     коллекторе это было бы неправдой ровно до тех пор, пока пользователь не сдастся.
     */
    SyncNowResponse: {
      /**
       * Sync Requested At
       * Format: date-time
       */
      sync_requested_at: string;
      /** Last Sync At */
      last_sync_at: string | null;
      /** Last Heartbeat At */
      last_heartbeat_at: string | null;
      /**
       * Collector Online
       * @description Heartbeat коллектора свежее 5 минут. Если нет — просьба ждёт запуска
       */
      collector_online: boolean;
    };
    /**
     * SyncRunResponse
     * @description Строка `sync_runs` (SPEC.md 3.3).
     */
    SyncRunResponse: {
      /** Id */
      id: number;
      /** Source */
      source: string;
      /**
       * Started At
       * Format: date-time
       */
      started_at: string;
      /** Finished At */
      finished_at: string | null;
      /** Deals Received */
      deals_received: number | null;
      /** Deals New */
      deals_new: number | null;
      /** Positions Rebuilt */
      positions_rebuilt: number | null;
      /** Server Utc Offset Minutes */
      server_utc_offset_minutes: number | null;
      /** Error */
      error: string | null;
    };
    /** SyncRunsResponse */
    SyncRunsResponse: {
      /** Items */
      items: components['schemas']['SyncRunResponse'][];
    };
    /**
     * TimezonesResponse
     * @description Список имён зон, которые принимает `PATCH /users/me`.
     */
    TimezonesResponse: {
      /**
       * Items
       * @description Имена таймзон IANA, отсортированы лексикографически
       */
      items: string[];
    };
    /**
     * UserResponse
     * @description Поля из SPEC.md 4, пункт 5.
     *
     *     Общая модель для `/auth/me`, `/auth/verify` и `/users/me` (S0-08): один пользователь
     *     описывается в схеме одним компонентом. Правка полей здесь меняет ответ всех трёх.
     */
    UserResponse: {
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /** Email */
      email: string;
      /** Display Name */
      display_name: string | null;
      /** Timezone */
      timezone: string;
      /** Day Boundary Hour */
      day_boundary_hour: number;
    };
    /**
     * UserUpdateRequest
     * @description Частичная правка профиля: отсутствующее поле не трогается.
     *
     *     `display_name` — единственное обнуляемое: явный `null` очищает имя, чего отсутствие
     *     поля не делает. `timezone` и `day_boundary_hour` обнулить нельзя, `null` в них —
     *     ошибка валидации.
     */
    UserUpdateRequest: {
      /**
       * Display Name
       * @description Отображаемое имя, не длиннее 100 символов. null или пустая строка очищают имя
       */
      display_name?: string | null;
      /**
       * Timezone
       * @description Имя таймзоны IANA, например Europe/Moscow
       */
      timezone?: string;
      /**
       * Day Boundary Hour
       * @description Час начала торгового дня в таймзоне пользователя, 0..23
       */
      day_boundary_hour?: number;
    };
    /** VerifyRequest */
    VerifyRequest: {
      /** Email */
      email: string;
      /** Code */
      code: string;
    };
    /** VersionResponse */
    VersionResponse: {
      /** Version */
      version: string;
    };
    /**
     * ErrorCode
     * @description Словарь кодов ошибок API — SPEC.md 5.1.
     * @enum {string}
     */
    ErrorCode:
      | 'account_already_exists'
      | 'account_archived'
      | 'account_not_found'
      | 'account_paused'
      | 'conflict'
      | 'forbidden'
      | 'forbidden_origin'
      | 'internal_error'
      | 'invalid_code'
      | 'method_not_allowed'
      | 'not_found'
      | 'not_mt5_account'
      | 'position_not_found'
      | 'rate_limited'
      | 'too_many_attempts'
      | 'unauthorized'
      | 'unprocessable_entity'
      | 'unsupported_media_type'
      | 'validation_error';
    /**
     * ApiError
     * @description Формат ошибки SPEC.md 5.1 — тело любого ответа с ошибкой.
     */
    ApiError: {
      error: {
        code: components['schemas']['ErrorCode'];
        message: string;
        details: {
          [key: string]: unknown;
        };
      };
    };
  };
  responses: never;
  parameters: never;
  requestBodies: never;
  headers: never;
  pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
  health_api_v1_health_get: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['HealthResponse'];
        };
      };
      /** @description Ошибка валидации запроса (validation_error) */
      400: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'validation_error';
              message: string;
              details: {
                fields: {
                  [key: string]: string;
                };
              };
            };
          };
        };
      };
      /** @description Требуется аутентификация (unauthorized) */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unauthorized';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Доступ запрещён (forbidden, forbidden_origin) */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'forbidden' | 'forbidden_origin';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Ресурс не найден (not_found) */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'not_found';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Метод не поддерживается (method_not_allowed) */
      405: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'method_not_allowed';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Конфликт состояния (conflict) */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'conflict';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Неподдерживаемый тип содержимого (unsupported_media_type) */
      415: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unsupported_media_type';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Запрос не может быть выполнен (unprocessable_entity) */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unprocessable_entity';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Слишком много запросов (rate_limited) */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'rate_limited';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Внутренняя ошибка сервера (internal_error) */
      500: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'internal_error';
              message: string;
              details: Record<string, never>;
            };
          };
        };
      };
    };
  };
  get_version_api_v1_version_get: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['VersionResponse'];
        };
      };
      /** @description Ошибка валидации запроса (validation_error) */
      400: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'validation_error';
              message: string;
              details: {
                fields: {
                  [key: string]: string;
                };
              };
            };
          };
        };
      };
      /** @description Требуется аутентификация (unauthorized) */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unauthorized';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Доступ запрещён (forbidden, forbidden_origin) */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'forbidden' | 'forbidden_origin';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Ресурс не найден (not_found) */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'not_found';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Метод не поддерживается (method_not_allowed) */
      405: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'method_not_allowed';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Конфликт состояния (conflict) */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'conflict';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Неподдерживаемый тип содержимого (unsupported_media_type) */
      415: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unsupported_media_type';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Запрос не может быть выполнен (unprocessable_entity) */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unprocessable_entity';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Слишком много запросов (rate_limited) */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'rate_limited';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Внутренняя ошибка сервера (internal_error) */
      500: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'internal_error';
              message: string;
              details: Record<string, never>;
            };
          };
        };
      };
    };
  };
  request_code_api_v1_auth_request_code_post: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': components['schemas']['RequestCodeRequest'];
      };
    };
    responses: {
      /** @description Successful Response */
      202: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['RequestCodeResponse'];
        };
      };
      /** @description Ошибка валидации запроса (validation_error) */
      400: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'validation_error';
              message: string;
              details: {
                fields: {
                  [key: string]: string;
                };
              };
            };
          };
        };
      };
      /** @description Требуется аутентификация (unauthorized) */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unauthorized';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Доступ запрещён (forbidden, forbidden_origin) */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'forbidden' | 'forbidden_origin';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Ресурс не найден (not_found) */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'not_found';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Метод не поддерживается (method_not_allowed) */
      405: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'method_not_allowed';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Конфликт состояния (conflict) */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'conflict';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Неподдерживаемый тип содержимого (unsupported_media_type) */
      415: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unsupported_media_type';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Запрос не может быть выполнен (unprocessable_entity) */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unprocessable_entity';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Слишком много запросов (rate_limited) */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'rate_limited';
              message: string;
              details: {
                /** @description Секунд до следующей попытки */
                retry_after: number;
              };
            };
          };
        };
      };
      /** @description Внутренняя ошибка сервера (internal_error) */
      500: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'internal_error';
              message: string;
              details: Record<string, never>;
            };
          };
        };
      };
    };
  };
  verify_api_v1_auth_verify_post: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': components['schemas']['VerifyRequest'];
      };
    };
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['UserResponse'];
        };
      };
      /** @description Ошибка валидации запроса (validation_error) */
      400: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'validation_error';
              message: string;
              details: {
                fields: {
                  [key: string]: string;
                };
              };
            };
          };
        };
      };
      /** @description Требуется аутентификация (unauthorized) */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unauthorized';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Доступ запрещён (forbidden, forbidden_origin) */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'forbidden' | 'forbidden_origin';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Ресурс не найден (not_found) */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'not_found';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Метод не поддерживается (method_not_allowed) */
      405: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'method_not_allowed';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Конфликт состояния (conflict) */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'conflict';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Неподдерживаемый тип содержимого (unsupported_media_type) */
      415: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unsupported_media_type';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Запрос не может быть выполнен (invalid_code, too_many_attempts, unprocessable_entity) */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'invalid_code' | 'too_many_attempts' | 'unprocessable_entity';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Слишком много запросов (rate_limited) */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'rate_limited';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Внутренняя ошибка сервера (internal_error) */
      500: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'internal_error';
              message: string;
              details: Record<string, never>;
            };
          };
        };
      };
    };
  };
  logout_api_v1_auth_logout_post: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      204: {
        headers: {
          [name: string]: unknown;
        };
        content?: never;
      };
      /** @description Ошибка валидации запроса (validation_error) */
      400: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'validation_error';
              message: string;
              details: {
                fields: {
                  [key: string]: string;
                };
              };
            };
          };
        };
      };
      /** @description Требуется аутентификация (unauthorized) */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unauthorized';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Доступ запрещён (forbidden, forbidden_origin) */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'forbidden' | 'forbidden_origin';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Ресурс не найден (not_found) */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'not_found';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Метод не поддерживается (method_not_allowed) */
      405: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'method_not_allowed';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Конфликт состояния (conflict) */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'conflict';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Неподдерживаемый тип содержимого (unsupported_media_type) */
      415: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unsupported_media_type';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Запрос не может быть выполнен (unprocessable_entity) */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unprocessable_entity';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Слишком много запросов (rate_limited) */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'rate_limited';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Внутренняя ошибка сервера (internal_error) */
      500: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'internal_error';
              message: string;
              details: Record<string, never>;
            };
          };
        };
      };
    };
  };
  me_api_v1_auth_me_get: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['UserResponse'];
        };
      };
      /** @description Ошибка валидации запроса (validation_error) */
      400: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'validation_error';
              message: string;
              details: {
                fields: {
                  [key: string]: string;
                };
              };
            };
          };
        };
      };
      /** @description Требуется аутентификация (unauthorized) */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unauthorized';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Доступ запрещён (forbidden, forbidden_origin) */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'forbidden' | 'forbidden_origin';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Ресурс не найден (not_found) */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'not_found';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Метод не поддерживается (method_not_allowed) */
      405: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'method_not_allowed';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Конфликт состояния (conflict) */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'conflict';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Неподдерживаемый тип содержимого (unsupported_media_type) */
      415: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unsupported_media_type';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Запрос не может быть выполнен (unprocessable_entity) */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unprocessable_entity';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Слишком много запросов (rate_limited) */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'rate_limited';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Внутренняя ошибка сервера (internal_error) */
      500: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'internal_error';
              message: string;
              details: Record<string, never>;
            };
          };
        };
      };
    };
  };
  read_me_api_v1_users_me_get: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['UserResponse'];
        };
      };
      /** @description Ошибка валидации запроса (validation_error) */
      400: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'validation_error';
              message: string;
              details: {
                fields: {
                  [key: string]: string;
                };
              };
            };
          };
        };
      };
      /** @description Требуется аутентификация (unauthorized) */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unauthorized';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Доступ запрещён (forbidden, forbidden_origin) */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'forbidden' | 'forbidden_origin';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Ресурс не найден (not_found) */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'not_found';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Метод не поддерживается (method_not_allowed) */
      405: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'method_not_allowed';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Конфликт состояния (conflict) */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'conflict';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Неподдерживаемый тип содержимого (unsupported_media_type) */
      415: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unsupported_media_type';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Запрос не может быть выполнен (unprocessable_entity) */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unprocessable_entity';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Слишком много запросов (rate_limited) */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'rate_limited';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Внутренняя ошибка сервера (internal_error) */
      500: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'internal_error';
              message: string;
              details: Record<string, never>;
            };
          };
        };
      };
    };
  };
  update_me_api_v1_users_me_patch: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': components['schemas']['UserUpdateRequest'];
      };
    };
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['UserResponse'];
        };
      };
      /** @description Ошибка валидации запроса (validation_error) */
      400: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'validation_error';
              message: string;
              details: {
                fields: {
                  [key: string]: string;
                };
              };
            };
          };
        };
      };
      /** @description Требуется аутентификация (unauthorized) */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unauthorized';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Доступ запрещён (forbidden, forbidden_origin) */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'forbidden' | 'forbidden_origin';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Ресурс не найден (not_found) */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'not_found';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Метод не поддерживается (method_not_allowed) */
      405: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'method_not_allowed';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Конфликт состояния (conflict) */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'conflict';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Неподдерживаемый тип содержимого (unsupported_media_type) */
      415: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unsupported_media_type';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Запрос не может быть выполнен (unprocessable_entity) */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unprocessable_entity';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Слишком много запросов (rate_limited) */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'rate_limited';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Внутренняя ошибка сервера (internal_error) */
      500: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'internal_error';
              message: string;
              details: Record<string, never>;
            };
          };
        };
      };
    };
  };
  list_timezones_api_v1_users_timezones_get: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['TimezonesResponse'];
        };
      };
      /** @description Список не менялся с версии из If-None-Match */
      304: {
        headers: {
          [name: string]: unknown;
        };
        content?: never;
      };
      /** @description Ошибка валидации запроса (validation_error) */
      400: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'validation_error';
              message: string;
              details: {
                fields: {
                  [key: string]: string;
                };
              };
            };
          };
        };
      };
      /** @description Требуется аутентификация (unauthorized) */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unauthorized';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Доступ запрещён (forbidden, forbidden_origin) */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'forbidden' | 'forbidden_origin';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Ресурс не найден (not_found) */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'not_found';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Метод не поддерживается (method_not_allowed) */
      405: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'method_not_allowed';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Конфликт состояния (conflict) */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'conflict';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Неподдерживаемый тип содержимого (unsupported_media_type) */
      415: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unsupported_media_type';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Запрос не может быть выполнен (unprocessable_entity) */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unprocessable_entity';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Слишком много запросов (rate_limited) */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'rate_limited';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Внутренняя ошибка сервера (internal_error) */
      500: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'internal_error';
              message: string;
              details: Record<string, never>;
            };
          };
        };
      };
    };
  };
  list_accounts_api_v1_accounts_get: {
    parameters: {
      query?: {
        /** @description Показать и архивные счета. По умолчанию они скрыты */
        include_archived?: boolean;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['AccountsResponse'];
        };
      };
      /** @description Ошибка валидации запроса (validation_error) */
      400: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'validation_error';
              message: string;
              details: {
                fields: {
                  [key: string]: string;
                };
              };
            };
          };
        };
      };
      /** @description Требуется аутентификация (unauthorized) */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unauthorized';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Доступ запрещён (forbidden, forbidden_origin) */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'forbidden' | 'forbidden_origin';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Ресурс не найден (not_found) */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'not_found';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Метод не поддерживается (method_not_allowed) */
      405: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'method_not_allowed';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Конфликт состояния (conflict) */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'conflict';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Неподдерживаемый тип содержимого (unsupported_media_type) */
      415: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unsupported_media_type';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Запрос не может быть выполнен (unprocessable_entity) */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unprocessable_entity';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Слишком много запросов (rate_limited) */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'rate_limited';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Внутренняя ошибка сервера (internal_error) */
      500: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'internal_error';
              message: string;
              details: Record<string, never>;
            };
          };
        };
      };
    };
  };
  create_account_api_v1_accounts_post: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': components['schemas']['AccountCreateRequest'];
      };
    };
    responses: {
      /** @description Successful Response */
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['AccountResponse'];
        };
      };
      /** @description Ошибка валидации запроса (validation_error) */
      400: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'validation_error';
              message: string;
              details: {
                fields: {
                  [key: string]: string;
                };
              };
            };
          };
        };
      };
      /** @description Требуется аутентификация (unauthorized) */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unauthorized';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Доступ запрещён (forbidden, forbidden_origin) */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'forbidden' | 'forbidden_origin';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Ресурс не найден (not_found) */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'not_found';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Метод не поддерживается (method_not_allowed) */
      405: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'method_not_allowed';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Конфликт состояния (account_already_exists, conflict) */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'account_already_exists' | 'conflict';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Неподдерживаемый тип содержимого (unsupported_media_type) */
      415: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unsupported_media_type';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Запрос не может быть выполнен (unprocessable_entity) */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unprocessable_entity';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Слишком много запросов (rate_limited) */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'rate_limited';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Внутренняя ошибка сервера (internal_error) */
      500: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'internal_error';
              message: string;
              details: Record<string, never>;
            };
          };
        };
      };
    };
  };
  delete_account_api_v1_accounts__account_id__delete: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        account_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      204: {
        headers: {
          [name: string]: unknown;
        };
        content?: never;
      };
      /** @description Ошибка валидации запроса (validation_error) */
      400: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'validation_error';
              message: string;
              details: {
                fields: {
                  [key: string]: string;
                };
              };
            };
          };
        };
      };
      /** @description Требуется аутентификация (unauthorized) */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unauthorized';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Доступ запрещён (forbidden, forbidden_origin) */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'forbidden' | 'forbidden_origin';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Ресурс не найден (account_not_found, not_found) */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'account_not_found' | 'not_found';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Метод не поддерживается (method_not_allowed) */
      405: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'method_not_allowed';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Конфликт состояния (conflict) */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'conflict';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Неподдерживаемый тип содержимого (unsupported_media_type) */
      415: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unsupported_media_type';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Запрос не может быть выполнен (unprocessable_entity) */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unprocessable_entity';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Слишком много запросов (rate_limited) */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'rate_limited';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Внутренняя ошибка сервера (internal_error) */
      500: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'internal_error';
              message: string;
              details: Record<string, never>;
            };
          };
        };
      };
    };
  };
  update_account_api_v1_accounts__account_id__patch: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        account_id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': components['schemas']['AccountUpdateRequest'];
      };
    };
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['AccountResponse'];
        };
      };
      /** @description Ошибка валидации запроса (validation_error) */
      400: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'validation_error';
              message: string;
              details: {
                fields: {
                  [key: string]: string;
                };
              };
            };
          };
        };
      };
      /** @description Требуется аутентификация (unauthorized) */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unauthorized';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Доступ запрещён (forbidden, forbidden_origin) */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'forbidden' | 'forbidden_origin';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Ресурс не найден (account_not_found, not_found) */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'account_not_found' | 'not_found';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Метод не поддерживается (method_not_allowed) */
      405: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'method_not_allowed';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Конфликт состояния (account_already_exists, conflict) */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'account_already_exists' | 'conflict';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Неподдерживаемый тип содержимого (unsupported_media_type) */
      415: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unsupported_media_type';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Запрос не может быть выполнен (account_archived, not_mt5_account, unprocessable_entity) */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'account_archived' | 'not_mt5_account' | 'unprocessable_entity';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Слишком много запросов (rate_limited) */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'rate_limited';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Внутренняя ошибка сервера (internal_error) */
      500: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'internal_error';
              message: string;
              details: Record<string, never>;
            };
          };
        };
      };
    };
  };
  pause_account_api_v1_accounts__account_id__pause_post: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        account_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['AccountResponse'];
        };
      };
      /** @description Ошибка валидации запроса (validation_error) */
      400: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'validation_error';
              message: string;
              details: {
                fields: {
                  [key: string]: string;
                };
              };
            };
          };
        };
      };
      /** @description Требуется аутентификация (unauthorized) */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unauthorized';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Доступ запрещён (forbidden, forbidden_origin) */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'forbidden' | 'forbidden_origin';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Ресурс не найден (account_not_found, not_found) */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'account_not_found' | 'not_found';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Метод не поддерживается (method_not_allowed) */
      405: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'method_not_allowed';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Конфликт состояния (conflict) */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'conflict';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Неподдерживаемый тип содержимого (unsupported_media_type) */
      415: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unsupported_media_type';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Запрос не может быть выполнен (account_archived, unprocessable_entity) */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'account_archived' | 'unprocessable_entity';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Слишком много запросов (rate_limited) */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'rate_limited';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Внутренняя ошибка сервера (internal_error) */
      500: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'internal_error';
              message: string;
              details: Record<string, never>;
            };
          };
        };
      };
    };
  };
  resume_account_api_v1_accounts__account_id__resume_post: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        account_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['AccountResponse'];
        };
      };
      /** @description Ошибка валидации запроса (validation_error) */
      400: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'validation_error';
              message: string;
              details: {
                fields: {
                  [key: string]: string;
                };
              };
            };
          };
        };
      };
      /** @description Требуется аутентификация (unauthorized) */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unauthorized';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Доступ запрещён (forbidden, forbidden_origin) */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'forbidden' | 'forbidden_origin';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Ресурс не найден (account_not_found, not_found) */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'account_not_found' | 'not_found';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Метод не поддерживается (method_not_allowed) */
      405: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'method_not_allowed';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Конфликт состояния (conflict) */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'conflict';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Неподдерживаемый тип содержимого (unsupported_media_type) */
      415: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unsupported_media_type';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Запрос не может быть выполнен (account_archived, unprocessable_entity) */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'account_archived' | 'unprocessable_entity';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Слишком много запросов (rate_limited) */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'rate_limited';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Внутренняя ошибка сервера (internal_error) */
      500: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'internal_error';
              message: string;
              details: Record<string, never>;
            };
          };
        };
      };
    };
  };
  archive_account_api_v1_accounts__account_id__archive_post: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        account_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['AccountResponse'];
        };
      };
      /** @description Ошибка валидации запроса (validation_error) */
      400: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'validation_error';
              message: string;
              details: {
                fields: {
                  [key: string]: string;
                };
              };
            };
          };
        };
      };
      /** @description Требуется аутентификация (unauthorized) */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unauthorized';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Доступ запрещён (forbidden, forbidden_origin) */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'forbidden' | 'forbidden_origin';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Ресурс не найден (account_not_found, not_found) */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'account_not_found' | 'not_found';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Метод не поддерживается (method_not_allowed) */
      405: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'method_not_allowed';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Конфликт состояния (conflict) */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'conflict';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Неподдерживаемый тип содержимого (unsupported_media_type) */
      415: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unsupported_media_type';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Запрос не может быть выполнен (unprocessable_entity) */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unprocessable_entity';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Слишком много запросов (rate_limited) */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'rate_limited';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Внутренняя ошибка сервера (internal_error) */
      500: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'internal_error';
              message: string;
              details: Record<string, never>;
            };
          };
        };
      };
    };
  };
  sync_now_api_v1_accounts__account_id__sync_now_post: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        account_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      202: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['SyncNowResponse'];
        };
      };
      /** @description Ошибка валидации запроса (validation_error) */
      400: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'validation_error';
              message: string;
              details: {
                fields: {
                  [key: string]: string;
                };
              };
            };
          };
        };
      };
      /** @description Требуется аутентификация (unauthorized) */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unauthorized';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Доступ запрещён (forbidden, forbidden_origin) */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'forbidden' | 'forbidden_origin';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Ресурс не найден (account_not_found, not_found) */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'account_not_found' | 'not_found';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Метод не поддерживается (method_not_allowed) */
      405: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'method_not_allowed';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Конфликт состояния (conflict) */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'conflict';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Неподдерживаемый тип содержимого (unsupported_media_type) */
      415: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unsupported_media_type';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Запрос не может быть выполнен (account_archived, account_paused, unprocessable_entity) */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'account_archived' | 'account_paused' | 'unprocessable_entity';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Слишком много запросов (rate_limited) */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'rate_limited';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Внутренняя ошибка сервера (internal_error) */
      500: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'internal_error';
              message: string;
              details: Record<string, never>;
            };
          };
        };
      };
    };
  };
  list_sync_runs_api_v1_accounts__account_id__sync_runs_get: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        account_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['SyncRunsResponse'];
        };
      };
      /** @description Ошибка валидации запроса (validation_error) */
      400: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'validation_error';
              message: string;
              details: {
                fields: {
                  [key: string]: string;
                };
              };
            };
          };
        };
      };
      /** @description Требуется аутентификация (unauthorized) */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unauthorized';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Доступ запрещён (forbidden, forbidden_origin) */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'forbidden' | 'forbidden_origin';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Ресурс не найден (account_not_found, not_found) */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'account_not_found' | 'not_found';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Метод не поддерживается (method_not_allowed) */
      405: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'method_not_allowed';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Конфликт состояния (conflict) */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'conflict';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Неподдерживаемый тип содержимого (unsupported_media_type) */
      415: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unsupported_media_type';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Запрос не может быть выполнен (unprocessable_entity) */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unprocessable_entity';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Слишком много запросов (rate_limited) */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'rate_limited';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Внутренняя ошибка сервера (internal_error) */
      500: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'internal_error';
              message: string;
              details: Record<string, never>;
            };
          };
        };
      };
    };
  };
  list_positions_api_v1_journal_positions_get: {
    parameters: {
      query?: {
        /** @description UUID счетов через запятую. Пусто — все неархивированные счета */
        account_ids?: string | null;
        status?: ('open' | 'closed') | null;
        /** @description Начало периода включительно. Сравнивается с временем закрытия, а у ещё открытых позиций — с временем открытия */
        from?: string | null;
        /** @description Конец периода, не включая границу */
        to?: string | null;
        /** @description Точное совпадение с symbol_norm */
        symbol?: string | null;
        direction?: ('long' | 'short') | null;
        /** @description Только закрытые позиции: у открытых итога нет */
        result?: ('win' | 'loss' | 'be') | null;
        /** @description Теги через запятую. Позиция должна нести их все */
        tags?: string | null;
        /** @description Заполнена ли рефлексия (`filled_at` не пуст) */
        has_reflection?: boolean | null;
        /** @description Поиск по символу и тексту заметки */
        q?: string | null;
        /** @description Сортировка задаётся как «поле:направление», поле — одно из close_time, open_time, net_pnl, symbol_norm, duration_seconds; направление — asc или desc */
        sort?: string;
        limit?: number;
        /** @description Курсор следующей страницы */
        cursor?: string | null;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['PositionsPage'];
        };
      };
      /** @description Ошибка валидации запроса (validation_error) */
      400: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'validation_error';
              message: string;
              details: {
                fields: {
                  [key: string]: string;
                };
              };
            };
          };
        };
      };
      /** @description Требуется аутентификация (unauthorized) */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unauthorized';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Доступ запрещён (forbidden, forbidden_origin) */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'forbidden' | 'forbidden_origin';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Ресурс не найден (account_not_found, not_found) */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'account_not_found' | 'not_found';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Метод не поддерживается (method_not_allowed) */
      405: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'method_not_allowed';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Конфликт состояния (conflict) */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'conflict';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Неподдерживаемый тип содержимого (unsupported_media_type) */
      415: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unsupported_media_type';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Запрос не может быть выполнен (unprocessable_entity) */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unprocessable_entity';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Слишком много запросов (rate_limited) */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'rate_limited';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Внутренняя ошибка сервера (internal_error) */
      500: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'internal_error';
              message: string;
              details: Record<string, never>;
            };
          };
        };
      };
    };
  };
  get_position_api_v1_journal_positions__position_id__get: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        position_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['PositionCard'];
        };
      };
      /** @description Ошибка валидации запроса (validation_error) */
      400: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'validation_error';
              message: string;
              details: {
                fields: {
                  [key: string]: string;
                };
              };
            };
          };
        };
      };
      /** @description Требуется аутентификация (unauthorized) */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unauthorized';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Доступ запрещён (forbidden, forbidden_origin) */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'forbidden' | 'forbidden_origin';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Ресурс не найден (not_found, position_not_found) */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'not_found' | 'position_not_found';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Метод не поддерживается (method_not_allowed) */
      405: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'method_not_allowed';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Конфликт состояния (conflict) */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'conflict';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Неподдерживаемый тип содержимого (unsupported_media_type) */
      415: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unsupported_media_type';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Запрос не может быть выполнен (unprocessable_entity) */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unprocessable_entity';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Слишком много запросов (rate_limited) */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'rate_limited';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Внутренняя ошибка сервера (internal_error) */
      500: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'internal_error';
              message: string;
              details: Record<string, never>;
            };
          };
        };
      };
    };
  };
  heartbeat_api_v1_ingest_heartbeat_post: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': components['schemas']['HeartbeatRequest'];
      };
    };
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['HeartbeatResponse'];
        };
      };
      /** @description Ошибка валидации запроса (validation_error) */
      400: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'validation_error';
              message: string;
              details: {
                fields: {
                  [key: string]: string;
                };
              };
            };
          };
        };
      };
      /** @description Требуется аутентификация (unauthorized) */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unauthorized';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Доступ запрещён (forbidden, forbidden_origin) */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'forbidden' | 'forbidden_origin';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Ресурс не найден (not_found) */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'not_found';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Метод не поддерживается (method_not_allowed) */
      405: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'method_not_allowed';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Конфликт состояния (conflict) */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'conflict';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Неподдерживаемый тип содержимого (unsupported_media_type) */
      415: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unsupported_media_type';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Запрос не может быть выполнен (unprocessable_entity) */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unprocessable_entity';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Слишком много запросов (rate_limited) */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'rate_limited';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Внутренняя ошибка сервера (internal_error) */
      500: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'internal_error';
              message: string;
              details: Record<string, never>;
            };
          };
        };
      };
    };
  };
  assignments_api_v1_internal_collector_assignments_get: {
    parameters: {
      query: {
        /** @description Идентификатор установки коллектора: латиница, цифры и . _ - : @, не длиннее 64 символов */
        collector_id: string;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['AssignmentListResponse'];
        };
      };
      /** @description Ошибка валидации запроса (validation_error) */
      400: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'validation_error';
              message: string;
              details: {
                fields: {
                  [key: string]: string;
                };
              };
            };
          };
        };
      };
      /** @description Требуется аутентификация (unauthorized) */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unauthorized';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Доступ запрещён (forbidden, forbidden_origin) */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'forbidden' | 'forbidden_origin';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Ресурс не найден (not_found) */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'not_found';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Метод не поддерживается (method_not_allowed) */
      405: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'method_not_allowed';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Конфликт состояния (conflict) */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'conflict';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Неподдерживаемый тип содержимого (unsupported_media_type) */
      415: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unsupported_media_type';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Запрос не может быть выполнен (unprocessable_entity) */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unprocessable_entity';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Слишком много запросов (rate_limited) */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'rate_limited';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Внутренняя ошибка сервера (internal_error) */
      500: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'internal_error';
              message: string;
              details: Record<string, never>;
            };
          };
        };
      };
    };
  };
  list_outbox_api_v1_dev_outbox_get: {
    parameters: {
      query?: {
        limit?: number;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['OutboxResponse'];
        };
      };
      /** @description Ошибка валидации запроса (validation_error) */
      400: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'validation_error';
              message: string;
              details: {
                fields: {
                  [key: string]: string;
                };
              };
            };
          };
        };
      };
      /** @description Требуется аутентификация (unauthorized) */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unauthorized';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Доступ запрещён (forbidden, forbidden_origin) */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'forbidden' | 'forbidden_origin';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Ресурс не найден (not_found) */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'not_found';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Метод не поддерживается (method_not_allowed) */
      405: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'method_not_allowed';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Конфликт состояния (conflict) */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'conflict';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Неподдерживаемый тип содержимого (unsupported_media_type) */
      415: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unsupported_media_type';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Запрос не может быть выполнен (unprocessable_entity) */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'unprocessable_entity';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Слишком много запросов (rate_limited) */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'rate_limited';
              message: string;
              details: {
                [key: string]: unknown;
              };
            };
          };
        };
      };
      /** @description Внутренняя ошибка сервера (internal_error) */
      500: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': {
            error: {
              /** @enum {string} */
              code: 'internal_error';
              message: string;
              details: Record<string, never>;
            };
          };
        };
      };
    };
  };
}
