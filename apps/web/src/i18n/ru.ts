/**
 * Единственное место, где живут строки интерфейса (CLAUDE.md, правила кода).
 * Структура готовится под второй язык: компоненты берут строки из `@/i18n`, а не отсюда.
 */
import { plural } from '@/lib/plural';

const SECONDS = ['секунду', 'секунды', 'секунд'] as const;

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
    accountSwitcherPlaceholder: 'Счета',
    accountSwitcherHint: 'Переключатель счетов появится вместе со счетами',
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
    sessionExpired: 'Сессия истекла. Войдите снова.',
  },
  errors: {
    invalidCode: 'Неверный код. Проверьте письмо и попробуйте ещё раз.',
    tooManyAttempts: 'Попытки исчерпаны. Запросите новый код.',
    rateLimited: (retryAfter: number) =>
      `Слишком много запросов. Повторите через ${retryAfter} ${plural(retryAfter, SECONDS)}.`,
    rateLimitedUnknownDelay: 'Слишком много запросов. Попробуйте позже.',
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
