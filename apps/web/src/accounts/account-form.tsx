import { useEffect, useState, type FormEvent } from 'react';

import { messageForError } from '@/api/error-message';
import { ApiRequestError, ERROR_CODE } from '@/api/errors';
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
  password: string;
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
      password: '',
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
    // Пароль с сервера не приходит и приходить не должен: поле всегда начинается пустым.
    password: '',
  };
}

function isPaletteColor(color: string): color is AccountColor {
  return (ACCOUNT_COLORS as readonly string[]).includes(color);
}

const DIGITS = /^\d+$/;

type FieldErrors = Partial<Record<'label' | 'server' | 'login' | 'password', string>>;

/**
 * Проверки до отправки. Сервер валидирует то же самое ещё раз (CLAUDE.md, граница API) —
 * здесь они затем, чтобы человек не ждал ответа ради забытого поля.
 */
function validate(values: Values, isCreate: boolean): FieldErrors {
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
    // При правке пустое поле значит «оставить сохранённый», при создании — что пароля нет.
    if (isCreate && values.password === '') {
      errors.password = t.accounts.formPasswordRequired;
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
          password: values.password,
        }
      : {}),
  };
}

/**
 * Тело PATCH — только изменённые поля. Отсутствие поля значит «не трогать», и это здесь
 * важнее, чем в настройках: присланные `server`, `login` или `password` возвращают счёт
 * в `pending`, то есть переименование счёта останавливало бы работающий синк.
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
    if (values.password !== '') {
      patch.password = values.password;
    }
  }
  return patch;
}

/**
 * Форма счёта: создание (в модальном окне списка) и правка (на странице счёта). Одна
 * форма на оба случая — иначе подсказка про инвесторский пароль, которая и есть главное
 * содержимое этого экрана, существовала бы в двух расходящихся копиях.
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

  // Второй путь к тому же телу запроса: если запрос упал, `onSuccess` не выполнится, а
  // пароль останется в кэше мутаций до сборщика мусора — пять минут после ухода формы с
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

  // Один и тот же промах — пароль у счёта не-MT5 — приходит двумя кодами: `400
  // validation_error` при создании и `422 not_mt5_account` при правке (ревью S1-06).
  // Оба ведут к одному полю, поэтому оба и разбираются здесь.
  const notMt5 = failure?.code === ERROR_CODE.notMt5Account;
  const serverErrors: FieldErrors = {
    label: failure?.fieldError('label') ?? undefined,
    server: failure?.fieldError('server') ?? undefined,
    login: failure?.fieldError('login') ?? undefined,
    password: failure?.fieldError('password') ?? (notMt5 ? t.errors.notMt5Account : undefined),
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
    const found = validate(values, isCreate);
    if (Object.keys(found).length > 0) {
      setLocalErrors(found);
      return;
    }
    if (patch !== null && Object.keys(patch).length === 0) {
      return;
    }
    const onSuccess = (saved: Account) => {
      // Пароль стирается из состояния сразу после успеха: форма правки остаётся на
      // экране, и введённое значение иначе продолжало бы жить в DOM.
      setValues((previous) => ({ ...previous, password: '' }));
      setSaved(true);
      // Вторая копия пароля — тело мутации. Форма правки со страницы счёта не уходит,
      // и размонтирование её не стирает: `variables` жили бы всю сессию.
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

          <Field id={`${idPrefix}-login`} label={t.accounts.loginLabel} error={errorFor('login')}>
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

          <Field
            id={`${idPrefix}-password`}
            label={t.accounts.passwordLabel}
            error={errorFor('password')}
            hint={
              <>
                <p className="text-sm text-foreground">{t.accounts.passwordWhy}</p>
                <p>{t.accounts.passwordWhere}</p>
                <p>{t.accounts.passwordNeverMain}</p>
                {isCreate ? null : <p>{t.accounts.passwordEditHint}</p>}
                {isCreate ? null : <p>{t.accounts.passwordResetsStatus}</p>}
              </>
            }
          >
            {(props) => (
              <Input
                {...props}
                type="password"
                value={values.password}
                // Не `current-password`: менеджер паролей иначе подставляет сюда пароль
                // от сайта, а нужен другой — инвесторский, от терминала.
                autoComplete="new-password"
                maxLength={200}
                onChange={(event) => change({ password: event.target.value })}
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
