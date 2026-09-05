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
     *     Форма ответа — голый массив, дословно по SPEC.md 5.6, а не конверт `{items}`, каким
     *     отдаёт список счетов `GET /accounts`. Расхождение осознанное: менять записанную в
     *     спеке форму контракта — отдельное решение (`CLAUDE.md` §8), а не побочный эффект
     *     задачи. Потребитель один и внутренний (коллектор, S1-08).
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
          'application/json': components['schemas']['AssignmentResponse'][];
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
