/**
 * Десятичные значения из API — строки, а не числа: деньги это `numeric(18,2)`, цены и
 * объёмы — `numeric(18,8)` (SPEC.md 2.2). Бэкенд отдаёт их строками намеренно, и
 * `Number(...)` здесь обесценил бы это решение: double держит 15–16 значащих цифр, а в
 * колонке их 18.
 *
 * Поэтому строка тут не разбирается в `number` нигде. Округление и деление идут на
 * `BigInt`, а разряды расставляются вручную — `Intl.NumberFormat` разбирает строку
 * точно только с ES2023 и печатает пробел разряда по-разному в разных движках, а формат
 * из SPEC.md 9.4 задан до символа.
 *
 * Всё, что не десятичное число, возвращается как `null`: подстановка «0» на месте
 * непрочитанного значения — худшая из возможных ошибок в журнале сделок.
 */

const DECIMAL_RE = /^([+-]?)(\d*)(?:\.(\d*))?$/;

/** Разделитель, который печатает человек в русской раскладке. */
const COMMA = /,/g;
/** Незначащие нули целой части: `007` — это `7`, а `000` — `0`. */
const LEADING_ZEROS = /^0+(?=\d)/;

/** Неразрывный пробел: разряд не должен переноситься на другую строку таблицы. */
const GROUP_SEPARATOR = '\u00a0';
const DECIMAL_SEPARATOR = ',';
const GROUP_SIZE = 3;
const CURRENCY_SYMBOL = '$';

/** SPEC.md 9.4: «Цены: по `symbols.digits`, иначе 5 знаков». */
export const DEFAULT_PRICE_DIGITS = 5;

const MONEY_DIGITS = 2;
const RATIO_DIGITS = 2;
/**
 * Два знака процента — ровно та точность, с которой доля приходит с сервера: четыре знака
 * доли это два знака процента (`docs/metrics.md` §3.2, решение принято там осознанно —
 * «чтобы 1/3 отличалась от 1/3 с одной сделкой разницы»).
 *
 * Округление до одного знака отняло бы у экрана этот разряд: на 2000 сделках одна сделка
 * двигает `winrate` в ответе и уже не двигала бы число на экране. Число, переставшее
 * отвечать на данные, — ровно тот отказ, ради которого сводку и считает сервер.
 */
const PERCENT_DIGITS = 2;
/** Долю в проценты переводит перенос запятой на два разряда. */
const PERCENT_SHIFT = 2;
const VOLUME_MIN_DIGITS = 2;
const VOLUME_MAX_DIGITS = 8;

export type DecimalSign = 'positive' | 'negative' | 'zero';

type ParsedDecimal = {
  readonly negative: boolean;
  /** Цифры до точки, без знака. */
  readonly whole: string;
  /** Цифры после точки. */
  readonly fraction: string;
};

export function parseDecimal(raw: string): ParsedDecimal | null {
  const match = DECIMAL_RE.exec(raw.trim());
  if (match === null) {
    return null;
  }
  const whole = match[2] ?? '';
  const fraction = match[3] ?? '';
  // `.` и `-` разбираются регэкспом, но числом не являются: хотя бы одна цифра нужна.
  if (whole === '' && fraction === '') {
    return null;
  }
  return { negative: match[1] === '-', whole: whole === '' ? '0' : whole, fraction };
}

function hasSignificantDigit(digits: string): boolean {
  return /[1-9]/.test(digits);
}

/**
 * Знак значения — им красится P&L (SPEC.md 9.4). Считается по цифрам, а не сравнением с
 * нулём: `-0.00` это ноль, а не убыток, и красным светиться не должен.
 */
export function decimalSign(raw: string): DecimalSign | null {
  const parsed = parseDecimal(raw);
  if (parsed === null) {
    return null;
  }
  if (!hasSignificantDigit(parsed.whole) && !hasSignificantDigit(parsed.fraction)) {
    return 'zero';
  }
  return parsed.negative ? 'negative' : 'positive';
}

function pow10(exponent: number): bigint {
  return 10n ** BigInt(exponent);
}

function digitsOf(parsed: ParsedDecimal): bigint {
  return BigInt(`${parsed.whole}${parsed.fraction}`);
}

/** Цифры значения, округлённые до `digits` знаков после точки; половина — от нуля. */
function scaleDigits(parsed: ParsedDecimal, digits: number): bigint {
  const extra = parsed.fraction.length - digits;
  if (extra <= 0) {
    return digitsOf(parsed) * pow10(-extra);
  }
  const divisor = pow10(extra);
  const value = digitsOf(parsed);
  const quotient = value / divisor;
  return (value % divisor) * 2n >= divisor ? quotient + 1n : quotient;
}

function splitScaled(scaled: bigint, digits: number): { whole: string; fraction: string } {
  const text = scaled.toString().padStart(digits + 1, '0');
  const cut = text.length - digits;
  return { whole: text.slice(0, cut), fraction: text.slice(cut) };
}

function groupWhole(whole: string): string {
  let grouped = '';
  for (let index = whole.length; index > 0; index -= GROUP_SIZE) {
    const start = Math.max(0, index - GROUP_SIZE);
    const chunk = whole.slice(start, index);
    grouped = grouped === '' ? chunk : `${chunk}${GROUP_SEPARATOR}${grouped}`;
  }
  return grouped;
}

function trimFraction(fraction: string, minDigits: number): string {
  let end = fraction.length;
  while (end > minDigits && fraction[end - 1] === '0') {
    end -= 1;
  }
  return fraction.slice(0, end);
}

/**
 * `-1 234,56` — число без единицы измерения. Хвостовые нули между `minDigits` и
 * `maxDigits` убираются: `0.10000000` лота это `0,10`, а не `0,10000000`.
 */
function formatFixed(raw: string, minDigits: number, maxDigits: number): string | null {
  const parsed = parseDecimal(raw);
  if (parsed === null) {
    return null;
  }
  const scaled = scaleDigits(parsed, maxDigits);
  const { whole, fraction } = splitScaled(scaled, maxDigits);
  const trimmed = trimFraction(fraction, minDigits);
  // Знак берётся после округления: `-0.004` с двумя знаками это ноль, а «-0,00» на
  // экране читается как крошечный убыток, которого нет.
  const negative = parsed.negative && scaled !== 0n;
  const body =
    trimmed === '' ? groupWhole(whole) : `${groupWhole(whole)}${DECIMAL_SEPARATOR}${trimmed}`;
  return `${negative ? '-' : ''}${body}`;
}

/** `-1 234,56 $` — SPEC.md 9.4. */
export function formatMoney(raw: string): string | null {
  const value = formatFixed(raw, MONEY_DIGITS, MONEY_DIGITS);
  return value === null ? null : `${value}${GROUP_SEPARATOR}${CURRENCY_SYMBOL}`;
}

/** Цена инструмента. Число знаков приходит из словаря символов, иначе пять. */
export function formatPrice(raw: string, digits: number = DEFAULT_PRICE_DIGITS): string | null {
  return formatFixed(raw, digits, digits);
}

/**
 * Объём в лотах. Два знака — минимум (`0.1` лота это `0,10`), но хвост не обрезается:
 * у части брокеров минимальный лот `0.001`, и `0,00` вместо него означало бы «ничего».
 */
export function formatVolume(raw: string): string | null {
  return formatFixed(raw, VOLUME_MIN_DIGITS, VOLUME_MAX_DIGITS);
}

/** Отношение (R) — число без валюты, два знака. */
export function formatRatio(raw: string): string | null {
  return formatFixed(raw, RATIO_DIGITS, RATIO_DIGITS);
}

/**
 * Доля 0…1 в проценты — `winrate` сводки (`docs/metrics.md` §3.2 отдаёт её долей с
 * четырьмя знаками, перевод в проценты и знак «%» это работа фронта).
 *
 * Умножения на 100 здесь нет: запятая переносится по цифрам, потому что `number` в этом
 * модуле не появляется нигде, а `0.5000 * 100` в double даёт не то, что напечатано.
 */
export function formatPercent(raw: string): string | null {
  const parsed = parseDecimal(raw);
  if (parsed === null) {
    return null;
  }
  const fraction = parsed.fraction.padEnd(PERCENT_SHIFT, '0');
  const shifted = `${parsed.negative ? '-' : ''}${parsed.whole}${fraction.slice(0, PERCENT_SHIFT)}.${fraction.slice(PERCENT_SHIFT)}`;
  const value = formatFixed(shifted, PERCENT_DIGITS, PERCENT_DIGITS);
  return value === null ? null : `${value}${GROUP_SEPARATOR}%`;
}

/**
 * Десятичный литерал запятой или точкой — к одному написанию: `1,10` и `1.10000000`
 * становятся `1.1`, `007` — `7`, `-0.0` — `0`. Ничего, кроме отбрасывания незначащих
 * нулей, тут не происходит: цифры остаются теми же, `number` по-прежнему не появляется.
 *
 * Нужна ровно затем, чтобы «изменено» в карточке позиции считалось по значению, а не по
 * написанию. Иначе форма, показавшая `1.1` там, где сервер хранит `1.10000000`, считала
 * бы себя изменённой вечно — и автосохранение слало бы один и тот же PUT по кругу.
 */
export function canonicalDecimal(raw: string): string | null {
  const parsed = parseDecimal(raw.replace(COMMA, '.'));
  if (parsed === null) {
    return null;
  }
  const whole = parsed.whole.replace(LEADING_ZEROS, '');
  const fraction = trimFraction(parsed.fraction, 0);
  const negative = parsed.negative && (hasSignificantDigit(whole) || hasSignificantDigit(fraction));
  const tail = fraction === '' ? '' : `.${fraction}`;
  return `${negative ? '-' : ''}${whole}${tail}`;
}

/**
 * Деление двух десятичных строк с округлением до `fractionDigits`. Потребитель один —
 * отношение R (`net_pnl / risk_amount`, SPEC.md 9.3).
 *
 * Через `BigInt`, а не через `number`: делимое приходит из `numeric(18,2)`, и путь
 * «строка → double → строка» вносил бы ошибку в единственное число экрана, которое
 * человек сравнивает со своим планом.
 */
export function divideDecimal(
  dividend: string,
  divisor: string,
  fractionDigits: number,
): string | null {
  const left = parseDecimal(dividend);
  const right = parseDecimal(divisor);
  if (left === null || right === null || fractionDigits < 0) {
    return null;
  }
  const denominator = digitsOf(right) * pow10(left.fraction.length);
  if (denominator === 0n) {
    return null;
  }
  // Один лишний разряд, чтобы округлить его же, а не отбросить: BigInt делит с
  // усечением, и без этого шага 0,999 превратилось бы в 0,99.
  const numerator = digitsOf(left) * pow10(right.fraction.length + fractionDigits + 1);
  const scaled = (numerator / denominator + 5n) / 10n;

  const { whole, fraction } = splitScaled(scaled, fractionDigits);
  const negative = left.negative !== right.negative && scaled !== 0n;
  const tail = fraction === '' ? '' : `.${fraction}`;
  return `${negative ? '-' : ''}${whole}${tail}`;
}
