/**
 * Автосохранение карточки позиции — SPEC.md 9.3, задержка 800 мс и индикатор «сохранено».
 *
 * Правило, вокруг которого построен хук: **правда о записи — ответ сервера, а не форма.**
 * Поэтому «изменено» считается сравнением двух тел — того, что собрала форма, и того,
 * что, по нашим сведениям, лежит на сервере. Из этого само собой выходит остальное:
 * успешное сохранение обнуляет разницу, потому что ответ кладётся в кэш; неудачное
 * ничего не трогает, поэтому набранное остаётся и в форме, и в очереди на отправку.
 *
 * Версий и `If-Match` в контракте нет (`S2-02`), и сверки `updated_at` здесь тоже нет —
 * намеренно. Переименование и удаление тега двигают `updated_at` у всех затронутых
 * записей (SPEC.md 5.4), то есть сверка ловила бы «конфликт» там, где эту позицию никто
 * не трогал. Побеждает последняя запись, ровно как решено на сервере.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

/** SPEC.md 9.3: «автосохранение с задержкой 800 мс». */
export const AUTOSAVE_DELAY_MS = 800;

export type SaveState =
  /** Форма совпадает с сервером, и в этой сессии её не сохраняли. */
  | 'clean'
  /** Есть изменения, отсчитывается задержка. */
  | 'scheduled'
  | 'saving'
  | 'saved'
  | 'failed'
  /** Тело не собирается: в поле не число. Слать нечего, и молчать об этом нельзя. */
  | 'invalid';

export type Autosave = {
  readonly state: SaveState;
  readonly error: unknown;
  /** Повторить последнюю неудачу. Тело берётся из формы заново, а не из памяти о провале. */
  readonly retry: () => void;
  /**
   * Сохранить немедленно. Нужен там, где ждать задержку нечем: уход с поля и закрытие
   * карточки. Возвращает промис, чтобы вызывающий мог дождаться конца записи.
   */
  readonly flush: () => Promise<void>;
};

export function useAutosave<TBody>({
  body,
  savedBody,
  save,
  delayMs = AUTOSAVE_DELAY_MS,
}: {
  /** Тело запроса из формы; `null` — форма не собирается в тело. */
  body: TBody | null;
  /** Что лежит на сервере по последнему полученному ответу. */
  savedBody: TBody;
  save: (body: TBody) => Promise<unknown>;
  delayMs?: number;
}): Autosave {
  const serialized = body === null ? null : JSON.stringify(body);
  const savedSerialized = JSON.stringify(savedBody);
  const dirty = serialized !== null && serialized !== savedSerialized;

  const [saving, setSaving] = useState(false);
  const [savedOnce, setSavedOnce] = useState(false);
  // Снимок запоминается вместе с ошибкой: пока в форме то же самое, повторять нечего —
  // тот же запрос вернёт тот же отказ. Любая правка снимает запрет сама.
  const [failure, setFailure] = useState<{ snapshot: string; error: unknown } | null>(null);

  const bodyRef = useRef(body);
  bodyRef.current = body;
  const savedRef = useRef(savedSerialized);
  savedRef.current = savedSerialized;
  const saveRef = useRef(save);
  saveRef.current = save;

  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const clearTimer = useCallback(() => {
    if (timer.current !== null) {
      clearTimeout(timer.current);
      timer.current = null;
    }
  }, []);

  const inFlight = useRef(false);
  /**
   * Что уже доехало до сервера. Отдельно от `savedBody`, потому что тот приходит из кэша
   * запроса — а при закрытии карточки её кэш обновляться уже некуда: компонент снимается
   * раньше. Без этой памяти дозапись на выходе повторяла бы только что отправленное тело.
   */
  const delivered = useRef<string | null>(null);
  const run = useCallback(async (): Promise<void> => {
    clearTimer();
    const current = bodyRef.current;
    if (current === null || inFlight.current) {
      return;
    }
    const snapshot = JSON.stringify(current);
    if (snapshot === savedRef.current || snapshot === delivered.current) {
      return;
    }
    inFlight.current = true;
    setSaving(true);
    try {
      await saveRef.current(current);
      delivered.current = snapshot;
      setFailure(null);
      setSavedOnce(true);
    } catch (error) {
      setFailure({ snapshot, error });
    } finally {
      inFlight.current = false;
      setSaving(false);
    }
  }, [clearTimer]);

  const blocked = failure !== null && failure.snapshot === serialized;

  useEffect(() => {
    if (!dirty || saving || blocked) {
      return;
    }
    timer.current = setTimeout(() => {
      void run();
    }, delayMs);
    return clearTimer;
    // Задержка отсчитывается заново на каждое изменение тела: это и есть debounce.
  }, [serialized, dirty, saving, blocked, delayMs, run, clearTimer]);

  const retry = useCallback(() => {
    setFailure(null);
    void run();
  }, [run]);

  const flush = useCallback((): Promise<void> => {
    clearTimer();
    return run();
  }, [clearTimer, run]);

  const state: SaveState = saving
    ? 'saving'
    : blocked
      ? 'failed'
      : body === null
        ? 'invalid'
        : dirty
          ? 'scheduled'
          : savedOnce
            ? 'saved'
            : 'clean';

  return { state, error: failure?.error ?? null, retry, flush };
}

/**
 * Дописать незаписанное при уходе с карточки и сообщить, что список журнала устарел.
 *
 * Без этого теряется ровно то, ради чего экран существует: человек дописал строку и
 * закрыл карточку раньше, чем истекли 800 мс. Список обновляется здесь, а не на каждом
 * успешном сохранении: у него курсорная пагинация, и сброс на каждое нажатие клавиши
 * перезапрашивал бы все загруженные страницы.
 */
export function useFlushOnUnmount(autosave: Autosave, onTouched: () => void): void {
  const latest = useRef({ autosave, onTouched, touched: false });
  latest.current.autosave = autosave;
  latest.current.onTouched = onTouched;
  if (autosave.state !== 'clean') {
    latest.current.touched = true;
  }

  useEffect(
    () => () => {
      const { autosave: current, onTouched: done, touched } = latest.current;
      if (!touched) {
        return;
      }
      void current.flush().finally(done);
    },
    [],
  );
}
