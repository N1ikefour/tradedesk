/**
 * Форма, у которой есть источник на сервере: состояние поля живёт локально, но обязано
 * догонять запись, когда та меняется под открытой карточкой.
 *
 * Правило одно: **ответ сервера принимается, только если человек ничего не набрал.**
 * Отсюда два случая, и оба обязательны.
 *
 * 1. Карточка открыта, запись перечитана — другой вкладкой, переименованием тега
 *    (SPEC.md 5.4 требует после него перечитать открытые карточки), просто повторным
 *    запросом. Форма, оставшаяся с прежними значениями, тут же считалась бы изменённой —
 *    и автосохранение записало бы **старое поверх нового**. Найдено в браузере: открытая
 *    карточка после перечитывания стёрла заметку, которой в её форме не было.
 * 2. Ответ на собственное сохранение. Он может отличаться от отправленного: написание
 *    тега задаёт словарь (`trend` при заведённом `Trend` вернётся как `Trend`). Не принять
 *    его — значит считать форму изменённой навсегда и слать один и тот же запрос по кругу.
 *
 * Во всех остальных случаях побеждает набранное: перезаписать поле, в котором человек
 * что-то пишет, нельзя ничем.
 */
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from 'react';

export type SyncedForm<T> = {
  readonly form: T;
  readonly setForm: Dispatch<SetStateAction<T>>;
  /** Запомнить форму на момент отправки — по ней узнаётся эхо собственного сохранения. */
  readonly markSent: () => void;
};

export function useSyncedForm<T>(serverForm: T): SyncedForm<T> {
  const [form, setForm] = useState<T>(serverForm);
  const formRef = useRef(form);
  formRef.current = form;
  const previousServer = useRef(serverForm);
  const sent = useRef<T | null>(null);

  useEffect(() => {
    const current = JSON.stringify(formRef.current);
    const untouched = current === JSON.stringify(previousServer.current);
    const echo = sent.current !== null && current === JSON.stringify(sent.current);
    previousServer.current = serverForm;
    if (untouched || echo) {
      setForm(serverForm);
    }
  }, [serverForm]);

  const markSent = useCallback(() => {
    sent.current = formRef.current;
  }, []);

  return { form, setForm, markSent };
}
