import { useEffect, useState, type FormEvent } from 'react';

import { messageForError } from '@/api/error-message';
import { ApiRequestError } from '@/api/errors';
import {
  useCreateAccount,
  useUpdateAccount,
  type Account,
  type AccountCreate,
  type AccountPlatform,
  type AccountUpdate,
} from '@/accounts/api';
import { ACCOUNT_COLORS, ACCOUNT_COLOR_NAMES, type AccountColor } from '@/accounts/palette';
import { platformName } from '@/accounts/status';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { t } from '@/i18n';

/** Только те источники, которые пользователь заводит сам. `csv` появится со своим импортом. */
const PLATFORMS: readonly AccountPlatform[] = ['mt5', 'manual'];

type Values = {
  platform: AccountPlatform;
  label: string;
  broker: string;
  isDemo: boolean;
  color: AccountColor;
  server: string;
  login: string;
};

function initialValues(account: Account | null): Values {
  if (account === null) {
    return {
      platform: 'mt5',
      label: '',
      broker: '',
      isDemo: false,
      color: ACCOUNT_COLORS[0],
      server: '',
      login: '',
    };
  }
  return {
    platform: account.platform,
    label: account.label,
    broker: account.broker ?? '',
    // Цвет счёта сервер мог назначить сам; он обязан остаться выбранным в форме.
    color: isPaletteColor(account.color) ? account.color : ACCOUNT_COLORS[0],
    isDemo: account.is_demo,
    server: account.server ?? '',
    login: account.login === null ? '' : String(account.login),
  };
}

function isPaletteColor(color: string): color is AccountColor {
  return (ACCOUNT_COLORS as readonly string[]).includes(color);
}

const DIGITS = /^\d+$/;

type FieldErrors = Partial<Record<'label' | 'server' | 'login', string>>;

/**
 * Проверки до отправки. Сервер валидирует то же самое ещё раз (CLAUDE.md, граница API) —
 * здесь они затем, чтобы человек не ждал ответа ради забытого поля.
 */
function validate(values: Values): FieldErrors {
  const errors: FieldErrors = {};
  if (values.label.trim() === '') {
    errors.label = t.accounts.formLabelRequired;
  }
  if (values.platform === 'mt5') {
    if (values.server.trim() === '') {
      errors.server = t.accounts.formServerRequired;
    }
    if (!DIGITS.test(values.login.trim())) {
      errors.login = t.accounts.formLoginRequired;
    }
  }
  return errors;
}

function buildCreate(values: Values): AccountCreate {
  const isMt5 = values.platform === 'mt5';
  return {
    label: values.label.trim(),
    platform: values.platform,
    is_demo: values.isDemo,
    color: values.color,
    broker: values.broker.trim() === '' ? null : values.broker.trim(),
    sort_order: 0,
    // Поля MT5 у счёта «вручную» — не пустые строки, а отсутствие: пустой `server`
    // сервер разберёт как заданный и отвергнет.
    ...(isMt5
      ? {
          server: values.server.trim(),
          login: Number(values.login.trim()),
        }
      : {}),
  };
}

/**
 * Тело PATCH — только изменённые поля. Отсутствие поля значит «не трогать», и это здесь
 * важнее, чем в настройках: изменённые `server` или `login` возвращают счёт в `pending`,
 * то есть переименование счёта останавливало бы работающий синк.
 */
function buildPatch(account: Account, values: Values): AccountUpdate {
  const patch: AccountUpdate = {};
  const label = values.label.trim();
  if (label !== account.label) {
    patch.label = label;
  }
  const broker = values.broker.trim() === '' ? null : values.broker.trim();
  if (broker !== account.broker) {
    patch.broker = broker;
  }
  if (values.isDemo !== account.is_demo) {
    patch.is_demo = values.isDemo;
  }
  if (values.color !== account.color) {
    patch.color = values.color;
  }
  if (account.platform === 'mt5') {
    const server = values.server.trim();
    if (server !== account.server) {
      patch.server = server;
    }
    const login = Number(values.login.trim());
    if (login !== account.login) {
      patch.login = login;
    }
  }
  return patch;
}

/**
 * Форма счёта: создание (в модальном окне списка) и правка (на странице счёта). Одна форма
 * на оба случая: набор полей у них совпадает целиком, а разошедшиеся копии одной формы —
 * это два разных ответа на вопрос «что нужно, чтобы завести счёт».
 *
 * Пароля счёта здесь нет с `T-07` (ADR-0006): в терминал MT5 входит человек, коллектор
 * подключается к открытому, и приложению пароль не нужен ни для чего.
 */
export function AccountForm({
  account,
  onDone,
  onCancel,
}: {
  account?: Account;
  /** Сохранённый счёт — тот, что вернул сервер: только в нём есть `id` нового счёта. */
  onDone?: (saved: Account) => void;
  onCancel?: () => void;
}) {
  const editing = account ?? null;
  const isCreate = editing === null;
  const [values, setValues] = useState<Values>(() => initialValues(editing));
  const [localErrors, setLocalErrors] = useState<FieldErrors>({});
  // Успех живёт отдельно от статуса мутации: после сохранения мутация стирается целиком
  // (см. `forget`), и сказать «сохранено» её состоянию уже нечем.
  const [saved, setSaved] = useState(false);

  const create = useCreateAccount();
  const update = useUpdateAccount(editing?.id ?? '');
  const mutation = isCreate ? create : update;

  // Второй путь к тому же телу запроса: если запрос упал, `onSuccess` не выполнится, и
  // тело останется в кэше мутаций до сборщика мусора — пять минут после ухода формы с
  // экрана. Стираем на её уходе. `forget` стабилен, так что это именно размонтирование, и
  // текст ошибки до него доживает.
  const { forget } = mutation;
  useEffect(() => forget, [forget]);

  const change = (patch: Partial<Values>) => {
    setValues((previous) => ({ ...previous, ...patch }));
    setLocalErrors({});
    setSaved(false);
    if (mutation.status !== 'idle') {
      mutation.reset();
    }
  };

  const failure = mutation.error instanceof ApiRequestError ? mutation.error : null;

  // Промах «поля MT5 у счёта не-MT5» приходит двумя кодами: `400 validation_error` при
  // создании и `422 not_mt5_account` при правке (ревью S1-06). Форма таких тел не
  // отправляет — поля MT5 она у другой платформы не показывает и не шлёт, — поэтому код
  // разбирается общим текстом ошибки (`messageForError`), а не привязкой к полю.
  const serverErrors: FieldErrors = {
    label: failure?.fieldError('label') ?? undefined,
    server: failure?.fieldError('server') ?? undefined,
    login: failure?.fieldError('login') ?? undefined,
  };
  const errorFor = (name: keyof FieldErrors) => localErrors[name] ?? serverErrors[name] ?? null;

  const isMt5 = values.platform === 'mt5';
  const patch = isCreate ? null : buildPatch(editing, values);
  const dirty = patch === null || Object.keys(patch).length > 0;

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (mutation.isPending) {
      return;
    }
    const found = validate(values);
    if (Object.keys(found).length > 0) {
      setLocalErrors(found);
      return;
    }
    if (patch !== null && Object.keys(patch).length === 0) {
      return;
    }
    const onSuccess = (saved: Account) => {
      setSaved(true);
      // Тело запроса живёт в кэше мутаций до сборщика мусора, а форма правки со страницы
      // счёта не уходит: `variables` лежали бы там всю сессию. Секрета в теле больше нет
      // (`T-07`), но на `forget` стоит и признак «сохранено» — см. `saved`.
      mutation.forget();
      onDone?.(saved);
    };
    if (patch === null) {
      create.mutate(buildCreate(values), { onSuccess });
    } else {
      update.mutate(patch, { onSuccess });
    }
  };

  const idPrefix = isCreate ? 'account-create' : `account-edit`;

  return (
    <form className="flex flex-col gap-5" onSubmit={handleSubmit} noValidate>
      <Field
        id={`${idPrefix}-platform`}
        label={t.accounts.platformLabel}
        hint={isCreate ? undefined : <p>{t.accounts.platformHint}</p>}
      >
        {(props) => (
          <Select
            {...props}
            value={values.platform}
            // Платформа определяет и набор полей, и способ получения сделок: сменить её
            // у существующего счёта нечем, кроме как завести новый.
            disabled={!isCreate}
            onChange={(event) => change({ platform: event.target.value as AccountPlatform })}
          >
            {PLATFORMS.map((platform) => (
              <option key={platform} value={platform}>
                {platformName(platform)}
              </option>
            ))}
          </Select>
        )}
      </Field>

      <Field
        id={`${idPrefix}-label`}
        label={t.accounts.labelLabel}
        hint={<p>{t.accounts.labelHint}</p>}
        error={errorFor('label')}
      >
        {(props) => (
          <Input
            {...props}
            value={values.label}
            placeholder={t.accounts.labelPlaceholder}
            maxLength={100}
            onChange={(event) => change({ label: event.target.value })}
          />
        )}
      </Field>

      <Field id={`${idPrefix}-broker`} label={t.accounts.brokerLabel}>
        {(props) => (
          <Input
            {...props}
            value={values.broker}
            placeholder={t.accounts.brokerPlaceholder}
            maxLength={100}
            onChange={(event) => change({ broker: event.target.value })}
          />
        )}
      </Field>

      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <input
            id={`${idPrefix}-demo`}
            type="checkbox"
            className="size-4 accent-primary"
            checked={values.isDemo}
            aria-describedby={`${idPrefix}-demo-hint`}
            onChange={(event) => change({ isDemo: event.target.checked })}
          />
          <Label htmlFor={`${idPrefix}-demo`}>{t.accounts.isDemoLabel}</Label>
        </div>
        <p id={`${idPrefix}-demo-hint`} className="text-xs text-muted-foreground">
          {t.accounts.isDemoHint}
        </p>
      </div>

      <ColorPicker
        idPrefix={idPrefix}
        value={values.color}
        onChange={(color) => change({ color })}
      />

      {isMt5 ? (
        <>
          <Field
            id={`${idPrefix}-server`}
            label={t.accounts.serverLabel}
            hint={<p>{t.accounts.serverHint}</p>}
            error={errorFor('server')}
          >
            {(props) => (
              <Input
                {...props}
                value={values.server}
                placeholder={t.accounts.serverPlaceholder}
                maxLength={100}
                onChange={(event) => change({ server: event.target.value })}
              />
            )}
          </Field>

          <Field
            id={`${idPrefix}-login`}
            label={t.accounts.loginLabel}
            error={errorFor('login')}
            hint={
              <>
                <p>{t.accounts.loginHint}</p>
                {isCreate ? null : <p>{t.accounts.formIdentityResetsStatus}</p>}
              </>
            }
          >
            {(props) => (
              <Input
                {...props}
                value={values.login}
                inputMode="numeric"
                placeholder={t.accounts.loginPlaceholder}
                maxLength={20}
                onChange={(event) => change({ login: event.target.value })}
              />
            )}
          </Field>
        </>
      ) : null}

      {mutation.isError ? (
        <Alert variant="destructive">
          {isCreate ? t.accounts.createFailed : t.accounts.saveFailed}{' '}
          {messageForError(mutation.error)}
        </Alert>
      ) : null}

      {!isCreate && saved && !dirty ? <Alert>{t.accounts.saved}</Alert> : null}

      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={mutation.isPending || !dirty}>
          {isCreate
            ? mutation.isPending
              ? t.accounts.creating
              : t.accounts.create
            : mutation.isPending
              ? t.accounts.saving
              : t.accounts.save}
        </Button>
        {onCancel === undefined ? null : (
          /* «Отмена» ничего не отправляет и ничего не меняет на сервере. */
          <Button type="button" variant="ghost" disabled={mutation.isPending} onClick={onCancel}>
            {t.common.cancel}
          </Button>
        )}
        {!isCreate && !dirty && !saved && update.status === 'idle' ? (
          <span className="text-xs text-muted-foreground">{t.accounts.noChanges}</span>
        ) : null}
      </div>
    </form>
  );
}

/**
 * Выбор цвета — группа радиокнопок, а не набор кликабельных кружков: цвет обязан быть
 * доступен с клавиатуры и назван словом, иначе выбирать его нечем и незрячему, и
 * дальтонику.
 */
function ColorPicker({
  idPrefix,
  value,
  onChange,
}: {
  idPrefix: string;
  value: AccountColor;
  onChange: (color: AccountColor) => void;
}) {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="text-sm leading-none font-medium">{t.accounts.colorLabel}</legend>
      <div className="flex flex-wrap gap-2 pt-1">
        {ACCOUNT_COLORS.map((color) => (
          <label key={color} className="relative cursor-pointer" title={ACCOUNT_COLOR_NAMES[color]}>
            <input
              type="radio"
              name={`${idPrefix}-color`}
              className="peer sr-only"
              value={color}
              checked={value === color}
              aria-label={ACCOUNT_COLOR_NAMES[color]}
              onChange={() => onChange(color)}
            />
            <span
              aria-hidden="true"
              style={{ backgroundColor: color }}
              className="block size-7 rounded-full ring-offset-2 ring-offset-background peer-checked:ring-2 peer-checked:ring-foreground peer-focus-visible:ring-2 peer-focus-visible:ring-ring"
            />
          </label>
        ))}
      </div>
      <p className="text-xs text-muted-foreground">{t.accounts.colorHint}</p>
    </fieldset>
  );
}
