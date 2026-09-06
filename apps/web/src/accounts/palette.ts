/**
 * Палитра счетов. Значения задаёт сервер (`AccountColor` в схеме OpenAPI), здесь только
 * порядок показа и подписи: список цветов API не отдаёт, а нарисовать образцы без него
 * нечем.
 *
 * Копия не расходится молча: `satisfies` не пропустит цвет, которого нет в схеме, а
 * `Exhaustive` — схему, в которой появился девятый цвет. Оба провала — на сборке.
 */
import type { components } from '@/api/schema';
import { t } from '@/i18n';

export type AccountColor = NonNullable<components['schemas']['AccountCreateRequest']['color']>;

export const ACCOUNT_COLORS = [
  '#2563eb',
  '#16a34a',
  '#dc2626',
  '#d97706',
  '#7c3aed',
  '#0891b2',
  '#db2777',
  '#65a30d',
] as const satisfies readonly AccountColor[];

type MissingColor = Exclude<AccountColor, (typeof ACCOUNT_COLORS)[number]>;

/** Пустой тип означает «в списке есть все цвета схемы». Иначе здесь ошибка компиляции. */
const _allColorsListed: MissingColor[] = [];
void _allColorsListed;

/** Подписи образцов: кружок без имени недоступен ни скринридеру, ни клавиатуре. */
export const ACCOUNT_COLOR_NAMES: Record<AccountColor, string> = t.accounts.colorNames;

export function accountColorName(color: string): string {
  return color in ACCOUNT_COLOR_NAMES ? ACCOUNT_COLOR_NAMES[color as AccountColor] : color;
}
