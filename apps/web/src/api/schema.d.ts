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
     * UserResponse
     * @description Поля из SPEC.md 4, пункт 5.
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
      | 'conflict'
      | 'forbidden'
      | 'forbidden_origin'
      | 'internal_error'
      | 'invalid_code'
      | 'method_not_allowed'
      | 'not_found'
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
