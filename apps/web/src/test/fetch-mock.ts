/**
 * Мок API для компонентных тестов: маршрутизация по методу и пути, а не по порядку
 * вызовов. Порядко-зависимый мок ломается от любой перестановки запросов и молча
 * подсовывает чужой ответ.
 */
import { vi } from 'vitest';

export type MockedCall = { method: string; path: string; body: unknown };

/**
 * `signal` отдаётся маршруту, чтобы можно было изобразить молчащее соединение: ответа нет,
 * ошибки нет, и запрос заканчивается только собственным таймаутом клиента.
 */
export type MockRoute = (
  call: MockedCall & { url: URL; signal: AbortSignal | null },
) => Response | Promise<Response>;

/** Ключ — `"<МЕТОД> <путь>"`, например `"POST /api/v1/auth/verify"`. */
export type RouteTable = Record<string, MockRoute>;

export function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

/** Тело ошибки в формате SPEC.md 5.1. */
export function errorResponse(
  status: number,
  code: string,
  message = 'ошибка',
  details: Record<string, unknown> = {},
): Response {
  return jsonResponse(status, { error: { code, message, details } });
}

export function emptyResponse(status = 204): Response {
  return new Response(null, { status });
}

function parseJson(text: string): unknown {
  if (text.length === 0) {
    return null;
  }
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

async function describeRequest(
  input: Request | URL | string,
  init?: RequestInit,
): Promise<MockedCall & { url: URL; signal: AbortSignal | null }> {
  if (input instanceof Request) {
    const body = parseJson(await input.clone().text());
    const url = new URL(input.url);
    return {
      method: input.method.toUpperCase(),
      url,
      path: url.pathname,
      body,
      signal: input.signal,
    };
  }
  const url = new URL(String(input), window.location.origin);
  const method = (init?.method ?? 'GET').toUpperCase();
  const body = typeof init?.body === 'string' ? parseJson(init.body) : null;
  return { method, url, path: url.pathname, body, signal: init?.signal ?? null };
}

export function installFetchMock(routes: RouteTable): { calls: MockedCall[] } {
  const calls: MockedCall[] = [];

  const implementation = async (input: Request | URL | string, init?: RequestInit) => {
    const call = await describeRequest(input, init);
    calls.push({ method: call.method, path: call.path, body: call.body });
    const route = routes[`${call.method} ${call.path}`];
    if (!route) {
      throw new Error(`Нет мока для ${call.method} ${call.path}`);
    }
    return route(call);
  };

  vi.stubGlobal('fetch', vi.fn(implementation));
  return { calls };
}
