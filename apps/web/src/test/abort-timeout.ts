import type { MockRoute } from '@/test/fetch-mock';

/**
 * Подмена `AbortSignal.timeout` управляемым сигналом. Иначе предел ожидания нечем привести
 * в действие: он длиной в десятки секунд, а `AbortSignal.timeout` заводит свой таймер мимо
 * подменённых часов vitest.
 */
export function stubAbortTimeout(signal: AbortSignal): () => void {
  const original = Object.getOwnPropertyDescriptor(AbortSignal, 'timeout');
  Object.defineProperty(AbortSignal, 'timeout', {
    value: () => signal,
    configurable: true,
    writable: true,
  });
  return () => {
    if (original === undefined) {
      Reflect.deleteProperty(AbortSignal, 'timeout');
      return;
    }
    Object.defineProperty(AbortSignal, 'timeout', original);
  };
}

/** Тот же обрыв, что приходит от настоящего `AbortSignal.timeout`. */
export function timeoutReason(): DOMException {
  return new DOMException('истекло время ожидания', 'TimeoutError');
}

/**
 * Соединение, которое приняли и не ответили: ни данных, ни ошибки. Закончиться оно может
 * только обрывом, поэтому обрыв здесь единственный выход из промиса, и отказ несёт причину
 * обрыва — как настоящий `fetch`. Повторный запрос получает сигнал уже оборванным: иначе
 * повтор висел бы вечно и прятал исход за таймаутом самого теста.
 */
export const silentRoute: MockRoute = ({ signal }) =>
  new Promise<Response>((_, reject) => {
    const fail = () => reject(signal?.reason ?? timeoutReason());
    if (signal?.aborted === true) {
      fail();
      return;
    }
    signal?.addEventListener('abort', fail);
  });
