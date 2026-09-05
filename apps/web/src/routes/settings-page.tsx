import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react';

import { messageForError } from '@/api/error-message';
import { ApiRequestError } from '@/api/errors';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { t } from '@/i18n';
import { formatHourOfDay, formatTradingDay, formatZonedDateTime } from '@/lib/format';
import {
  buildTimeZoneOptions,
  filterTimeZoneOptions,
  groupTimeZoneOptions,
  isKnownTimeZone,
  withSelectedTimeZone,
} from '@/lib/time-zones';
import { useProfile, useUpdateProfile, type Profile, type ProfileUpdate } from '@/user/profile';

/** Пример времени должен идти сам: замерший на минуте час выглядит сломанным. */
const CLOCK_TICK_MS = 30_000;

const HOURS = Array.from({ length: 24 }, (_, hour) => hour);

type FormValues = {
  displayName: string;
  timezone: string;
  dayBoundaryHour: number;
};

function toFormValues(user: Profile): FormValues {
  return {
    displayName: user.display_name ?? '',
    timezone: user.timezone,
    dayBoundaryHour: user.day_boundary_hour,
  };
}

/** Пустое поле и поле из пробелов — это «очистить имя», то есть `null` (контракт S0-08). */
function normalizeName(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === '' ? null : trimmed;
}

/**
 * Тело PATCH — только изменённые поля: отсутствие поля означает «не трогать», и слать
 * неизменённое значит перезаписывать то, чего человек не редактировал.
 */
function buildPatch(user: Profile, values: FormValues): ProfileUpdate {
  const patch: ProfileUpdate = {};
  const name = normalizeName(values.displayName);
  if (name !== user.display_name) {
    patch.display_name = name;
  }
  if (values.timezone !== user.timezone) {
    patch.timezone = values.timezone;
  }
  if (values.dayBoundaryHour !== user.day_boundary_hour) {
    patch.day_boundary_hour = values.dayBoundaryHour;
  }
  return patch;
}

type FieldControlProps = {
  id: string;
  'aria-invalid': boolean;
  'aria-describedby': string | undefined;
};

function Field({
  id,
  label,
  hint,
  error,
  children,
}: {
  id: string;
  label: string;
  hint?: string;
  error?: string | null;
  children: (props: FieldControlProps) => ReactNode;
}) {
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [hint === undefined ? null : hintId, error ? errorId : null]
    .filter((value): value is string => value !== null)
    .join(' ');

  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor={id}>{label}</Label>
      {children({
        id,
        'aria-invalid': Boolean(error),
        'aria-describedby': describedBy === '' ? undefined : describedBy,
      })}
      {hint === undefined ? null : (
        <p id={hintId} className="text-xs text-muted-foreground">
          {hint}
        </p>
      )}
      {error ? (
        <p id={errorId} role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}

function SettingsForm({ user }: { user: Profile }) {
  const [values, setValues] = useState<FormValues>(() => toFormValues(user));
  const [timeZoneQuery, setTimeZoneQuery] = useState('');
  const [now, setNow] = useState<Date>(() => new Date());
  const update = useUpdateProfile();

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), CLOCK_TICK_MS);
    return () => window.clearInterval(timer);
  }, []);

  // Правка снимает прошлый результат: и «сохранено» под изменёнными полями, и ошибку
  // у поля, которое человек уже исправляет, говорят о состоянии, которого больше нет.
  const change = (patch: Partial<FormValues>) => {
    setValues((previous) => ({ ...previous, ...patch }));
    if (update.status !== 'idle') {
      update.reset();
    }
  };

  // Смещения зависят от даты (переход на летнее время), но список не должен
  // перестраиваться каждую минуту вслед за часами — берётся момент открытия экрана.
  const options = useMemo(() => buildTimeZoneOptions(new Date(), user.timezone), [user.timezone]);
  const matches = useMemo(
    () => filterTimeZoneOptions(options, timeZoneQuery),
    [options, timeZoneQuery],
  );
  const groups = useMemo(
    () => groupTimeZoneOptions(withSelectedTimeZone(matches, options, values.timezone)),
    [matches, options, values.timezone],
  );

  const patch = buildPatch(user, values);
  const dirty = Object.keys(patch).length > 0;

  const failure = update.error instanceof ApiRequestError ? update.error : null;
  const nameError = failure?.fieldError('display_name') ?? null;
  const timeZoneError = failure?.fieldError('timezone') ?? null;
  const hourError = failure?.fieldError('day_boundary_hour') ?? null;

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!dirty || update.isPending) {
      return;
    }
    update.mutate(patch);
  };

  return (
    <form className="flex flex-col gap-6" onSubmit={handleSubmit} noValidate>
      <Card>
        <CardContent className="flex flex-col gap-5 p-6">
          <Field id="settings-email" label={t.settings.emailLabel} hint={t.settings.emailHint}>
            {(props) => <Input {...props} value={user.email} readOnly />}
          </Field>

          <Field
            id="settings-display-name"
            label={t.settings.displayNameLabel}
            hint={t.settings.displayNameHint}
            error={nameError}
          >
            {(props) => (
              <Input
                {...props}
                value={values.displayName}
                placeholder={t.settings.displayNamePlaceholder}
                maxLength={100}
                autoComplete="nickname"
                onChange={(event) => change({ displayName: event.target.value })}
              />
            )}
          </Field>

          <div className="flex flex-col gap-2">
            <Field id="settings-timezone-search" label={t.settings.timezoneSearchLabel}>
              {(props) => (
                <Input
                  {...props}
                  type="search"
                  value={timeZoneQuery}
                  placeholder={t.settings.timezoneSearchPlaceholder}
                  onChange={(event) => setTimeZoneQuery(event.target.value)}
                />
              )}
            </Field>

            <Field
              id="settings-timezone"
              label={t.settings.timezoneLabel}
              hint={t.settings.timezoneHint}
              error={timeZoneError}
            >
              {(props) => (
                <Select
                  {...props}
                  value={values.timezone}
                  onChange={(event) => change({ timezone: event.target.value })}
                >
                  {groups.map((group) => (
                    <optgroup key={group.region} label={group.region}>
                      {group.options.map((option) => (
                        <option key={option.name} value={option.name}>
                          {option.label}
                        </option>
                      ))}
                    </optgroup>
                  ))}
                </Select>
              )}
            </Field>

            {matches.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t.settings.timezoneSearchEmpty}</p>
            ) : null}
          </div>

          <Field
            id="settings-day-boundary"
            label={t.settings.dayBoundaryLabel}
            hint={t.settings.dayBoundaryHint}
            error={hourError}
          >
            {(props) => (
              <Select
                {...props}
                value={String(values.dayBoundaryHour)}
                onChange={(event) => change({ dayBoundaryHour: Number(event.target.value) })}
              >
                {HOURS.map((hour) => (
                  <option key={hour} value={hour}>
                    {formatHourOfDay(hour)}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        </CardContent>
      </Card>

      <TimePreview now={now} timeZone={values.timezone} dayBoundaryHour={values.dayBoundaryHour} />

      {update.isError ? (
        <Alert variant="destructive">
          {t.settings.saveFailed} {messageForError(update.error)}
        </Alert>
      ) : null}

      {update.isSuccess && !dirty ? <Alert>{t.settings.saved}</Alert> : null}

      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={!dirty || update.isPending}>
          {update.isPending ? t.settings.saving : t.settings.save}
        </Button>
        {/* «Отмена» возвращает значения сервера и ничего не отправляет. */}
        <Button
          type="button"
          variant="ghost"
          disabled={!dirty || update.isPending}
          onClick={() => {
            setValues(toFormValues(user));
            if (update.status !== 'idle') {
              update.reset();
            }
          }}
        >
          {t.settings.cancel}
        </Button>
      </div>
    </form>
  );
}

/**
 * Живой пример — единственное место, где смена таймзоны видна сразу, до сохранения
 * (тикет S0-08, развилка 2). Он считается от значений формы, а не от сохранённого
 * профиля: иначе человек выбирал бы зону вслепую.
 */
function TimePreview({
  now,
  timeZone,
  dayBoundaryHour,
}: {
  now: Date;
  timeZone: string;
  dayBoundaryHour: number;
}) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-1 p-6">
        <h2 className="text-sm font-medium">{t.settings.previewTitle}</h2>
        {isKnownTimeZone(timeZone) ? null : (
          <p className="text-sm text-destructive">{t.settings.timezoneUnknown(timeZone)}</p>
        )}
        <p className="text-base">{t.settings.previewNow(formatZonedDateTime(now, timeZone))}</p>
        <p className="text-sm text-muted-foreground">
          {t.settings.previewTradingDay(
            formatTradingDay(now, timeZone, dayBoundaryHour),
            formatHourOfDay(dayBoundaryHour),
          )}
        </p>
      </CardContent>
    </Card>
  );
}

/** Экран настроек — SPEC.md 9.1 `/settings`: имя, таймзона, начало торгового дня. */
export function SettingsPage() {
  const profile = useProfile();

  return (
    <section className="mx-auto flex w-full max-w-2xl flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">{t.pages.settings}</h1>
        <p className="text-sm text-muted-foreground">{t.settings.hint}</p>
      </div>

      {profile.isPending ? (
        <p className="text-sm text-muted-foreground">{t.common.loading}</p>
      ) : null}

      {profile.isError ? (
        <div className="flex flex-col items-start gap-3">
          <Alert variant="destructive">
            {t.settings.loadFailed} {messageForError(profile.error)}
          </Alert>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              void profile.refetch();
            }}
            disabled={profile.isFetching}
          >
            {t.common.retry}
          </Button>
        </div>
      ) : null}

      {/* Форма пересоздаётся под другого пользователя: чужой ввод в полях недопустим. */}
      {profile.data ? <SettingsForm key={profile.data.id} user={profile.data} /> : null}
    </section>
  );
}
