/**
 * Запись журнала: поля формы ⇄ тело `PUT /journal/positions/{id}/entry`.
 *
 * ⚠️ Тело собирается **значением типа `JournalEntryUpdate`**, а не по кусочкам с
 * приведением. В схеме у него нет ни одного необязательного поля (SPEC.md 5.4: `PUT`
 * заменяет запись целиком), поэтому забытое поле — ошибка компиляции, а не молча стёртая
 * заметка. Ровно поэтому здесь одна функция на всё тело и ни одного `Partial`.
 *
 * Деньги и цены уходят строками. `number` не появляется нигде: `planned_*` это
 * `numeric(18,8)`, `risk_amount` — `numeric(18,2)`, а double держит 15–16 значащих цифр
 * (`CLAUDE.md` §2). Значение приводится к одному написанию (`canonicalDecimal`) — иначе
 * форма, показавшая `1.1` там, где сервер хранит `1.10000000`, считалась бы изменённой
 * вечно, и автосохранение слало бы один и тот же запрос по кругу.
 */
import type { JournalEntryDetail, JournalEntryUpdate } from '@/journal/api';
import { canonicalDecimal, decimalSign } from '@/lib/decimal';

/** Пределы сервера (`journal/schemas.py`). Здесь они не валидация, а край поля ввода. */
export const MAX_TAGS = 20;
export const MAX_TAG_LENGTH = 64;
export const MAX_TEXT_LENGTH = 20_000;

export type EntryForm = {
  readonly notes: string;
  readonly tags: readonly string[];
  readonly plannedEntry: string;
  readonly plannedSl: string;
  readonly plannedTp: string;
  readonly riskAmount: string;
};

export type EntryField = 'plannedEntry' | 'plannedSl' | 'plannedTp' | 'riskAmount';

export const EMPTY_ENTRY_FORM: EntryForm = {
  notes: '',
  tags: [],
  plannedEntry: '',
  plannedSl: '',
  plannedTp: '',
  riskAmount: '',
};

/**
 * Значение сервера в поле: то же число, без хвоста незначащих нулей и с запятой —
 * остальные числа на экране печатаются по SPEC.md 9.4 тоже с запятой, и поле, которое
 * одно во всей карточке показывает точку, читается как чужое. Обратно принимается любое
 * написание: `canonicalDecimal` разбирает и запятую, и точку.
 */
function toInput(value: string | null): string {
  if (value === null) {
    return '';
  }
  return (canonicalDecimal(value) ?? value).replace('.', ',');
}

export function entryFormFrom(entry: JournalEntryDetail | null): EntryForm {
  if (entry === null) {
    return EMPTY_ENTRY_FORM;
  }
  return {
    notes: entry.notes ?? '',
    tags: [...entry.tags],
    plannedEntry: toInput(entry.planned_entry),
    plannedSl: toInput(entry.planned_sl),
    plannedTp: toInput(entry.planned_tp),
    riskAmount: toInput(entry.risk_amount),
  };
}

/**
 * Текст поля → значение для тела. Пусто — `null` (очистка выражается явным `null`,
 * SPEC.md 5.4), не число — `undefined`: это не «очистить», а «не отправлять вовсе».
 */
function toDecimal(raw: string): string | null | undefined {
  const text = raw.trim();
  if (text === '') {
    return null;
  }
  return canonicalDecimal(text) ?? undefined;
}

/** Текст, как его сохранит сервер: `strip()`, а пустой — `null`. */
function toText(raw: string): string | null {
  const text = raw.trim();
  return text === '' ? null : text;
}

export type EntryErrors = Partial<Record<EntryField, 'number' | 'positive'>>;

export function entryErrors(form: EntryForm): EntryErrors {
  const errors: EntryErrors = {};
  for (const field of ['plannedEntry', 'plannedSl', 'plannedTp'] as const) {
    if (toDecimal(form[field]) === undefined) {
      errors[field] = 'number';
    }
  }
  const risk = toDecimal(form.riskAmount);
  if (risk === undefined) {
    errors.riskAmount = 'number';
  } else if (risk !== null && decimalSign(risk) !== 'positive') {
    // Строго больше нуля — не вкус: ноль дал бы деление на ноль в R, минус перевернул бы
    // ему знак. «Не задано» выражается пустым полем, а не нулём.
    errors.riskAmount = 'positive';
  }
  return errors;
}

/**
 * Форма → тело целиком. `null` означает «отправлять нечего»: в поле не число, и запрос
 * ушёл бы `400`. Частичное тело здесь построить невозможно — тип не даёт.
 */
export function entryBody(form: EntryForm): JournalEntryUpdate | null {
  if (Object.keys(entryErrors(form)).length > 0) {
    return null;
  }
  const plannedEntry = toDecimal(form.plannedEntry);
  const plannedSl = toDecimal(form.plannedSl);
  const plannedTp = toDecimal(form.plannedTp);
  const riskAmount = toDecimal(form.riskAmount);
  if (
    plannedEntry === undefined ||
    plannedSl === undefined ||
    plannedTp === undefined ||
    riskAmount === undefined
  ) {
    return null;
  }
  return {
    notes: toText(form.notes),
    tags: [...form.tags],
    planned_entry: plannedEntry,
    planned_sl: plannedSl,
    planned_tp: plannedTp,
    risk_amount: riskAmount,
  };
}

export type TagRejection = 'empty' | 'comma' | 'duplicate' | 'limit';

/**
 * Тег из поля ввода → чип. Правила те же, что у сервера (`normalize_tag`): пробелы по
 * краям срезаются, повтор без учёта регистра — не новый тег, запятая запрещена (по ней
 * разделяется фильтр `?tags=` в журнале, и такой тег нельзя было бы найти).
 */
export function addTag(
  tags: readonly string[],
  raw: string,
): { tags: readonly string[]; rejected: TagRejection | null } {
  const tag = raw.trim().slice(0, MAX_TAG_LENGTH);
  if (tag === '') {
    return { tags, rejected: 'empty' };
  }
  if (tag.includes(',')) {
    return { tags, rejected: 'comma' };
  }
  const folded = tag.toLocaleLowerCase();
  if (tags.some((existing) => existing.toLocaleLowerCase() === folded)) {
    return { tags, rejected: 'duplicate' };
  }
  if (tags.length >= MAX_TAGS) {
    return { tags, rejected: 'limit' };
  }
  return { tags: [...tags, tag], rejected: null };
}
