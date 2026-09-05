/**
 * Форматирование — SPEC.md 9.4. Одно место на всё приложение: `toFixed` и локальные
 * `Intl.*` по компонентам расходятся между экранами.
 *
 * Деньги и цены появятся вместе с экранами, которые их показывают.
 */
const LOCALE = 'ru-RU';

const DATE_TIME = new Intl.DateTimeFormat(LOCALE, {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
});

/**
 * `02.09.2026 17:03` в таймзоне браузера. API отдаёт UTC (ISO с `Z`).
 * Таймзона пользователя из профиля подключается вместе с настройками (S0-08).
 */
export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  // Intl разделяет дату и время запятой и ставит неразрывные пробелы (U+202F, U+00A0).
  // Приводим к обычному: иначе строка не находится поиском по странице.
  return DATE_TIME.format(date)
    .replace(/[\u202f\u00a0]/g, ' ')
    .replace(', ', ' ');
}
