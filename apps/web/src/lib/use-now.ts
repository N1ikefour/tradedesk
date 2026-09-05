import { useEffect, useState } from 'react';

/**
 * Текущий момент, обновляемый по таймеру. Относительное время («2 мин назад», SPEC.md 9.4)
 * без него застывает на значении первого рендера и выглядит достоверным, будучи неверным.
 */
export function useNow(intervalMs: number): Date {
  const [now, setNow] = useState<Date>(() => new Date());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), intervalMs);
    return () => window.clearInterval(timer);
  }, [intervalMs]);

  return now;
}
