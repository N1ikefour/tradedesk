/**
 * Единственное место, где живут строки интерфейса (CLAUDE.md, правила кода).
 * Структура готовится под второй язык: компоненты берут строки из `@/i18n`, а не отсюда.
 */
import { plural } from '@/lib/plural';

const SECONDS = ['секунду', 'секунды', 'секунд'] as const;
const MINUTES = ['минуту', 'минуты', 'минут'] as const;

/**
 * Окно лимита на запрос кода — час (SPEC.md 4), поэтому трёхзначные секунды здесь норма.
 * «Повторите через 522 секунды» человек не переводит в минуты в уме.
 */
function duration(totalSeconds: number): string {
  if (totalSeconds < 90) {
    return `${totalSeconds} ${plural(totalSeconds, SECONDS)}`;
  }
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  const head = `${minutes} ${plural(minutes, MINUTES)}`;
  // Секунды остаются видимыми: иначе счётчик кажется зависшим на целую минуту.
  return seconds === 0 ? head : `${head} ${seconds} ${plural(seconds, SECONDS)}`;
}

export const ru = {
  app: {
    name: 'TradeDesk',
  },
  common: {
    loading: 'Загрузка…',
    retry: 'Повторить',
    close: 'Закрыть',
  },
  nav: {
    dashboard: 'Дашборд',
    journal: 'Журнал',
    calendar: 'Календарь',
    accounts: 'Счета',
    settings: 'Настройки',
    devOutbox: 'Письма (dev)',
  },
  header: {
    // Место под переключатель счетов (SPEC.md 9.2). Сам переключатель — задача S1-11.
    // Подписи у слота нет: слово «Счета» уже занято пунктом меню рядом.
    accountSwitcherHint: 'Здесь появится переключатель счетов',
    logout: 'Выйти',
    menu: 'Меню',
  },
  theme: {
    switchToLight: 'Включить светлую тему',
    switchToDark: 'Включить тёмную тему',
  },
  login: {
    title: 'Вход',
    emailStepHint: 'Введите адрес — пришлём код для входа.',
    emailLabel: 'Электронная почта',
    emailPlaceholder: 'trader@example.com',
    requestCode: 'Получить код',
    requestingCode: 'Отправляем…',
    codeLabel: 'Код из письма',
    codeStepHint: (email: string) => `Код отправлен на ${email}. Он действует несколько минут.`,
    codePlaceholder: '000000',
    submit: 'Войти',
    verifying: 'Проверяем…',
    changeEmail: 'Изменить адрес',
    resend: 'Отправить код ещё раз',
    devOutboxLink: 'Открыть письма (dev)',
    codeResent: (email: string) => `Новый код отправлен на ${email}.`,
    sessionExpired: 'Сессия истекла. Войдите снова.',
    sessionCheckFailed: 'Не удалось проверить, вошли ли вы. Проверьте соединение и повторите.',
  },
  errors: {
    // Бэкенд отдаёт `invalid_code` на три ситуации: неверный код, просроченный код и
    // любой ввод после исчерпания попыток (код к этому моменту погашен). Сузить текст до
    // «проверьте письмо» значит отправить человека за кодом, который уже не сработает.
    invalidCode: 'Код неверный или устарел. Проверьте письмо или запросите новый.',
    tooManyAttempts: 'Попытки исчерпаны. Запросите новый код.',
    rateLimited: (retryAfter: number) =>
      `Слишком много запросов. Повторите через ${duration(retryAfter)}.`,
    rateLimitedUnknownDelay: 'Слишком много запросов. Попробуйте позже.',
    // Лимит на запрос кода считается по адресу (SPEC.md 4), поэтому адрес назван:
    // иначе непонятно, что достаточно исправить опечатку, а не ждать.
    rateLimitedFor: (email: string, retryAfter: number) =>
      `Слишком много запросов кода для ${email}. Повторите через ${duration(retryAfter)}.`,
    rateLimitedUnknownDelayFor: (email: string) =>
      `Слишком много запросов кода для ${email}. Попробуйте позже.`,
    validation: 'Проверьте введённые данные.',
    unauthorized: 'Нужно войти заново.',
    forbiddenOrigin: 'Запрос отклонён: приложение открыто по чужому адресу.',
    notFound: 'Запрошенные данные не найдены.',
    network: 'Сервер не отвечает. Проверьте соединение и повторите.',
    unknown: 'Что-то пошло не так. Попробуйте ещё раз.',
  },
  stub: {
    // Экраны маршрутов SPEC.md 9.1, которых ещё нет: роутер и layout проверяемы,
    // содержимое приходит своими задачами.
    note: 'Экран появится в одной из следующих задач.',
  },
  pages: {
    dashboard: 'Дашборд',
    journal: 'Журнал',
    position: 'Позиция',
    calendar: 'Календарь',
    accounts: 'Счета',
    account: 'Счёт',
    settings: 'Настройки',
    notFound: 'Страница не найдена',
    notFoundHint: 'Такого адреса нет. Вернитесь на главную.',
    goHome: 'На главную',
  },
  outbox: {
    title: 'Письма (dev)',
    hint: 'Локальная почта: сюда попадают письма с кодами входа. В проде страницы нет.',
    refresh: 'Обновить',
    empty: 'Писем пока нет. Запросите код на странице входа.',
    columnTo: 'Кому',
    columnSubject: 'Тема',
    columnCreatedAt: 'Когда',
    columnBody: 'Текст',
    backToLogin: 'К форме входа',
    loadFailed: 'Не удалось загрузить письма.',
  },
} as const;
