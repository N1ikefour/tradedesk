/** Русские формы числа: 1 секунда, 2 секунды, 5 секунд. Формы задаёт словарь i18n. */
export function plural(count: number, forms: readonly [string, string, string]): string {
  const abs = Math.abs(count) % 100;
  const tail = abs % 10;
  if (abs > 10 && abs < 20) {
    return forms[2];
  }
  if (tail > 1 && tail < 5) {
    return forms[1];
  }
  if (tail === 1) {
    return forms[0];
  }
  return forms[2];
}
