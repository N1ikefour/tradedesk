/**
 * Шов под второй язык: компоненты импортируют `t` отсюда и не знают, какой словарь
 * подставлен. В v1 язык один (SPEC.md 14), поэтому выбор статический.
 */
import { ru } from '@/i18n/ru';

export type Messages = typeof ru;

export const t: Messages = ru;
