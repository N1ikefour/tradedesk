import { describe, expect, it } from 'vitest';

import {
  canonicalDecimal,
  decimalSign,
  divideDecimal,
  formatMoney,
  formatPrice,
  formatPercent,
  formatRatio,
  formatVolume,
  sumDecimals,
} from '@/lib/decimal';

/** Разделитель разрядов — неразрывный пробел, и в ожиданиях он написан явно. */
const NB = '\u00a0';

describe('formatMoney', () => {
  it('печатает формат SPEC.md 9.4', () => {
    expect(formatMoney('-1234.56')).toBe(`-1${NB}234,56${NB}$`);
    expect(formatMoney('1234.5')).toBe(`1${NB}234,50${NB}$`);
    expect(formatMoney('0')).toBe(`0,00${NB}$`);
    expect(formatMoney('999')).toBe(`999,00${NB}$`);
    expect(formatMoney('1234567.89')).toBe(`1${NB}234${NB}567,89${NB}$`);
  });

  it('не теряет цифры, которых не держит double — ради этого деньги и приходят строкой', () => {
    const exact = '9007199254740993.01';

    expect(formatMoney(exact)).toBe(`9${NB}007${NB}199${NB}254${NB}740${NB}993,01${NB}$`);
    // Тот же путь через число: значение меняется молча, и на экране была бы не та сумма.
    expect(String(Number(exact))).not.toContain('740993');
  });

  it('округляет половину от нуля, а не к чётному', () => {
    expect(formatMoney('1.005')).toBe(`1,01${NB}$`);
    expect(formatMoney('-1.005')).toBe(`-1,01${NB}$`);
    expect(formatMoney('2.675')).toBe(`2,68${NB}$`);
  });

  it('не показывает минус там, где после округления ноль', () => {
    expect(formatMoney('-0.004')).toBe(`0,00${NB}$`);
    expect(formatMoney('-0.00')).toBe(`0,00${NB}$`);
  });

  it('на нечисле возвращает null, а не ноль', () => {
    expect(formatMoney('')).toBeNull();
    expect(formatMoney('abc')).toBeNull();
    expect(formatMoney('1,5')).toBeNull();
    expect(formatMoney('1e5')).toBeNull();
    expect(formatMoney('-')).toBeNull();
  });
});

describe('decimalSign', () => {
  it('различает прибыль, убыток и ноль', () => {
    expect(decimalSign('12.34')).toBe('positive');
    expect(decimalSign('-0.01')).toBe('negative');
    expect(decimalSign('0.00')).toBe('zero');
  });

  it('минус на нуле остаётся нулём: красить убытком нечего', () => {
    expect(decimalSign('-0.00')).toBe('zero');
  });

  it('нечисло не притворяется нулём', () => {
    expect(decimalSign('нет')).toBeNull();
  });
});

describe('formatPrice и formatVolume', () => {
  it('цена — пять знаков по умолчанию', () => {
    expect(formatPrice('1.2')).toBe('1,20000');
    expect(formatPrice('1.234567')).toBe('1,23457');
    expect(formatPrice('68000.5', 2)).toBe(`68${NB}000,50`);
  });

  it('объём — минимум два знака, но мелкий лот не обрезается', () => {
    expect(formatVolume('0.10000000')).toBe('0,10');
    expect(formatVolume('1')).toBe('1,00');
    expect(formatVolume('0.00100000')).toBe('0,001');
  });
});

describe('divideDecimal', () => {
  it('считает R без обращения к double', () => {
    expect(divideDecimal('150.00', '100.00', 2)).toBe('1.50');
    expect(divideDecimal('-75.00', '50.00', 2)).toBe('-1.50');
    expect(divideDecimal('1.00', '3.00', 2)).toBe('0.33');
    expect(divideDecimal('2.00', '3.00', 2)).toBe('0.67');
  });

  it('не сваливается в double: R считается на BigInt и на границах numeric(18,2)', () => {
    // Каждая строка убивает свою подмену на `Number(dividend) / Number(divisor)`:
    // на первой double теряет цифру (…994.00) при любом округлении; вторая ловит
    // `.toFixed(2)` (2,675 хранится как 2,674999…82 и печатается как 2.67); третья —
    // `Math.round(v * 100)`, где 1,005 × 100 даёт 100.49999999999999.
    expect(divideDecimal('9007199254740993.01', '1', 2)).toBe('9007199254740993.01');
    expect(divideDecimal('2.675', '1', 2)).toBe('2.68');
    expect(divideDecimal('1.005', '1', 2)).toBe('1.01');
  });

  it('деление на ноль и на мусор — null, а не бесконечность', () => {
    expect(divideDecimal('10.00', '0', 2)).toBeNull();
    expect(divideDecimal('10.00', '0.00', 2)).toBeNull();
    expect(divideDecimal('10.00', 'нет', 2)).toBeNull();
  });

  it('ноль в частном не получает минуса', () => {
    expect(divideDecimal('0.00', '-100.00', 2)).toBe('0.00');
  });

  it('результат готов к показу через formatRatio', () => {
    const value = divideDecimal('-250.00', '100.00', 2);

    expect(value).not.toBeNull();
    expect(formatRatio(value as string)).toBe('-2,50');
  });
});

describe('canonicalDecimal', () => {
  it('приводит написание к одному виду, не трогая значение', () => {
    expect(canonicalDecimal('1.10000000')).toBe('1.1');
    expect(canonicalDecimal('1,1')).toBe('1.1');
    expect(canonicalDecimal('007')).toBe('7');
    expect(canonicalDecimal('0.50')).toBe('0.5');
    expect(canonicalDecimal('-0.0')).toBe('0');
    expect(canonicalDecimal('  -12.30  ')).toBe('-12.3');
  });

  it('не теряет цифр за пределами double', () => {
    expect(canonicalDecimal('123456789012.12345678')).toBe('123456789012.12345678');
  });

  it('не число — null, а не подставленный ноль', () => {
    expect(canonicalDecimal('около 1.1')).toBeNull();
    expect(canonicalDecimal('')).toBeNull();
    expect(canonicalDecimal('-')).toBeNull();
  });
});

describe('formatPercent', () => {
  it('переводит долю сводки в проценты (docs/metrics.md §3.2)', () => {
    expect(formatPercent('0.5000')).toBe(`50,00${NB}%`);
    expect(formatPercent('0.6667')).toBe(`66,67${NB}%`);
    expect(formatPercent('0.0000')).toBe(`0,00${NB}%`);
    expect(formatPercent('1')).toBe(`100,00${NB}%`);
  });

  it('не теряет разряд, который сервер посчитал: одна сделка из 2000 видна на экране', () => {
    // 1029/2000 и 1030/2000 — соседние винрейты большого счёта. С одним знаком процента
    // они напечатались бы одинаково, и число перестало бы отвечать на данные.
    expect(formatPercent('0.5145')).toBe(`51,45${NB}%`);
    expect(formatPercent('0.5150')).toBe(`51,50${NB}%`);
  });

  it('округляет половину вверх — как калькулятор, а не как double', () => {
    expect(formatPercent('0.33335')).toBe(`33,34${NB}%`);
    // Тот же перевод через число даёт 66.66499999999999 и потерянный разряд.
    expect(formatPercent('0.66665')).toBe(`66,67${NB}%`);
  });

  it('не число — не проценты', () => {
    expect(formatPercent('')).toBeNull();
    expect(formatPercent('половина')).toBeNull();
  });
});

describe('sumDecimals', () => {
  it('складывает деньги дней в итог недели', () => {
    expect(sumDecimals(['10.00', '-2.50', '0.25'])).toBe('7.75');
    expect(sumDecimals(['-1779.72', '1779.72'])).toBe('0.00');
  });

  it('не теряет копейку там, где её теряет double', () => {
    // 0.1 + 0.2 в double это 0.30000000000000004, и итог недели переставал бы совпадать
    // с суммой её же дней — ровно то расхождение, которого экран не имеет права давать.
    expect(sumDecimals(['0.1', '0.2'])).toBe('0.3');
    // Восемнадцать значащих цифр: в double их 15–16, и последняя была бы выдумана.
    // Копейка выбрана не любая: с `0.01` итог совпадает и у double — округление до двух
    // знаков прячет ошибку, и тест прошёл бы поверх реализации на Number. С `0.02` не
    // прячет, и в этом весь смысл случая.
    expect(sumDecimals(['9999999999999999.99', '0.02'])).toBe('10000000000000000.01');
    // Восемь знаков после запятой — масштаб цен и объёмов (`numeric(18,8)`, SPEC.md 3.2).
    // Деньги в два знака double складывает верно почти всегда; ломается он здесь, и
    // складывать этой же функцией однажды будут именно их.
    expect(sumDecimals(['0.00000001', '0.00000002', '99999999.99999999'])).toBe(
      '100000000.00000002',
    );
  });

  it('приводит слагаемые к одному масштабу, а не складывает копейки с рублями', () => {
    expect(sumDecimals(['1', '0.05', '2.5'])).toBe('3.55');
  });

  it('нечитаемое слагаемое обнуляет весь итог, а не выпадает из него', () => {
    // Итог, собранный из части слагаемых, неотличим от верного — и потому опаснее прочерка.
    expect(sumDecimals(['10.00', 'нет'])).toBeNull();
    expect(sumDecimals(['10.00', ''])).toBeNull();
  });

  it('складывать нечего — это ноль', () => {
    expect(sumDecimals([])).toBe('0');
  });
});
