/**
 * Отметка «код уже отправлен» — единственное, что переживает уход со страницы входа.
 *
 * Шаг ввода кода жил в состоянии компонента, а `/dev/outbox` — соседний маршрут, а не
 * вложенный: переход туда размонтирует форму, и возврат поднимал её заново с первого
 * шага (X-16). Пока код лежит только на локальной странице писем, путь «запросил код →
 * ушёл за ним → вернулся» — основной способ войти, а не редкий случай.
 *
 * Хранится ровно адрес и время запроса. Самого кода здесь нет и быть не может: он
 * секрет на один вход, и в хранилище браузера ему делать нечего.
 *
 * `sessionStorage`, а не `localStorage`: отметка описывает незаконченную попытку входа
 * в этой вкладке, а не настройку рабочего места. Закрыли вкладку — попытки больше нет.
 */

const STORAGE_KEY = 'td.login.codeRequest.v1';

/** Срок жизни кода — SPEC.md §4: 10 минут. */
export const CODE_TTL_MS = 10 * 60 * 1000;

type CodeRequest = { readonly email: string; readonly requestedAt: number };

export type RestoredCodeRequest =
  | { readonly status: 'none' }
  | { readonly status: 'pending'; readonly email: string }
  | { readonly status: 'expired'; readonly email: string };

/**
 * Хранилище браузера бросает исключение, а не возвращает пустоту, когда сайту оно
 * запрещено. Вход — не та вещь, ради удобства которой экран имеет право не открыться.
 */
function readRaw(): string | null {
  try {
    return window.sessionStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

/** Значение из хранилища — чужой ввод: его правит рука и старая версия приложения. */
function parse(raw: string | null): CodeRequest | null {
  if (raw === null) {
    return null;
  }
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    return null;
  }
  if (typeof value !== 'object' || value === null) {
    return null;
  }
  const record = value as Record<string, unknown>;
  const { email, requestedAt } = record;
  if (typeof email !== 'string' || email.length === 0) {
    return null;
  }
  if (typeof requestedAt !== 'number' || !Number.isFinite(requestedAt)) {
    return null;
  }
  return { email, requestedAt };
}

/**
 * Что делать со страницей входа при открытии. Просроченная отметка не восстанавливает
 * шаг и тут же стирается: иначе объяснение «код истёк» всплывало бы ещё раз на пустом
 * месте. Проверка срока здесь — вежливость клиента, а не приговор: годен код или нет,
 * знает только сервер, и он же отвечает «неверный код», если часы браузера соврали.
 *
 * Отметка из будущего тоже считается просроченной. Разность с ней отрицательна, так что
 * одна проверка на срок держала бы её вечно — до закрытия вкладки. Сценарий бытовой:
 * часы ушли вперёд, код запрошен, часы поправили — и человек сидит на шаге ввода с
 * заведомо мёртвым кодом.
 */
export function restoreCodeRequest(now: number): RestoredCodeRequest {
  const record = parse(readRaw());
  if (record === null) {
    return { status: 'none' };
  }
  const age = now - record.requestedAt;
  if (age >= CODE_TTL_MS || age < 0) {
    clearCodeRequest();
    return { status: 'expired', email: record.email };
  }
  return { status: 'pending', email: record.email };
}

export function rememberCodeRequest(email: string, now: number): void {
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ email, requestedAt: now }));
  } catch {
    // Шаг просто не переживёт уход со страницы — это лучше, чем упавший вход.
  }
}

export function clearCodeRequest(): void {
  try {
    window.sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // См. выше.
  }
}
