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
