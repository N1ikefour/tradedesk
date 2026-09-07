/**
 * Блоки «План» и «Заметки и теги» — SPEC.md 9.3. Визуально их два, запись журнала одна:
 * оба блока сохраняются одним `PUT /journal/positions/{id}/entry`, потому что он заменяет
 * запись целиком. Два независимых сохранения по одному маршруту затирали бы друг друга —
 * тот, кто отправил вторым, стёр бы поля первого.
 *
 * Поэтому здесь одна форма, один автосейв и один индикатор, показанный дважды.
 */
import { useCallback, useId, useMemo, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { X } from 'lucide-react';

import { t } from '@/i18n';
import {
  useJournalTags,
  useSaveEntry,
  type JournalEntryUpdate,
  type PositionCard,
} from '@/journal/api';
import {
  addTag,
  entryBody,
  entryErrors,
  entryFormFrom,
  MAX_TAGS,
  MAX_TAG_LENGTH,
  MAX_TEXT_LENGTH,
  type EntryErrors,
  type EntryField,
  type EntryForm,
  type TagRejection,
} from '@/journal/entry-form';
import { SaveIndicator } from '@/journal/save-indicator';
import { useAutosave, useFlushOnUnmount, type Autosave } from '@/journal/use-autosave';
import { useSyncedForm } from '@/journal/use-synced-form';
import { canonicalDecimal, divideDecimal, formatRatio } from '@/lib/decimal';

const RATIO_DIGITS = 2;

/** Пустая запись — тоже полное тело: у `JournalEntryUpdate` нет необязательных полей. */
const EMPTY_ENTRY_BODY: JournalEntryUpdate = {
  notes: null,
  tags: [],
  planned_entry: null,
  planned_sl: null,
  planned_tp: null,
  risk_amount: null,
};

function fieldError(kind: 'number' | 'positive' | undefined): string | null {
  if (kind === undefined) {
    return null;
  }
  return kind === 'number' ? t.position.numberInvalid : t.position.riskNotPositive;
}

function rejectionMessage(rejection: TagRejection | null): string | null {
  switch (rejection) {
    case 'comma':
      return t.position.tagComma;
    case 'limit':
      return t.position.tagsLimit(MAX_TAGS);
    default:
      return null;
  }
}

export function EntryBlocks({
  position,
  onTouched,
}: {
  position: PositionCard;
  onTouched: () => void;
}) {
  const entry = position.journal_entry;
  const serverForm = useMemo(() => entryFormFrom(entry), [entry]);
  const savedBody = useMemo(() => entryBody(serverForm) ?? EMPTY_ENTRY_BODY, [serverForm]);

  const { form, setForm, markSent } = useSyncedForm(serverForm);

  const { mutateAsync } = useSaveEntry(position.id);
  const save = useCallback(
    (body: JournalEntryUpdate) => {
      markSent();
      return mutateAsync(body);
    },
    [markSent, mutateAsync],
  );

  const body = useMemo(() => entryBody(form), [form]);
  const autosave = useAutosave({ body, savedBody, save });
  useFlushOnUnmount(autosave, onTouched);

  const errors = entryErrors(form);
  const flush = useCallback(() => {
    void autosave.flush();
  }, [autosave]);

  const update = (patch: Partial<EntryForm>) => {
    setForm((current) => ({ ...current, ...patch }));
  };

  return (
    <>
      <PlanBlock
        position={position}
        form={form}
        errors={errors}
        autosave={autosave}
        onChange={update}
        onBlur={flush}
      />
      <NotesBlock form={form} autosave={autosave} onChange={update} onBlur={flush} />
    </>
  );
}

function PlanBlock({
  position,
  form,
  errors,
  autosave,
  onChange,
  onBlur,
}: {
  position: PositionCard;
  form: EntryForm;
  errors: EntryErrors;
  autosave: Autosave;
  onChange: (patch: Partial<EntryForm>) => void;
  onBlur: () => void;
}) {
  const id = useId();
  const ratio = useMemo(() => {
    // Считается по тому, что сейчас в поле: число обязано отвечать на ввод сразу.
    // Запасной формулы SPEC.md 9.3 (через `planned_sl` и `contract_size`) здесь нет —
    // `contract_size` живёт в словаре символов, а его наружу не отдаёт никто.
    const risk = canonicalDecimal(form.riskAmount);
    if (errors.riskAmount !== undefined || risk === null) {
      return null;
    }
    const value = divideDecimal(position.net_pnl, risk, RATIO_DIGITS);
    return value === null ? null : formatRatio(value);
  }, [position.net_pnl, form.riskAmount, errors.riskAmount]);

  // Патч на каждое поле объявлен явно: вычисляемый ключ превратил бы `Partial<EntryForm>`
  // в объект с индексной сигнатурой, то есть снял бы проверку имён полей.
  const fields: readonly {
    field: EntryField;
    label: string;
    patch: (value: string) => Partial<EntryForm>;
  }[] = [
    {
      field: 'plannedEntry',
      label: t.position.plannedEntry,
      patch: (value) => ({ plannedEntry: value }),
    },
    { field: 'plannedSl', label: t.position.plannedSl, patch: (value) => ({ plannedSl: value }) },
    { field: 'plannedTp', label: t.position.plannedTp, patch: (value) => ({ plannedTp: value }) },
    {
      field: 'riskAmount',
      label: t.position.riskAmount,
      patch: (value) => ({ riskAmount: value }),
    },
  ];

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 p-5">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="flex flex-col gap-1">
            <h2 className="text-sm font-medium">{t.position.planTitle}</h2>
            <p className="text-xs text-muted-foreground">{t.position.planHint}</p>
          </div>
          <SaveIndicator autosave={autosave} />
        </div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {fields.map(({ field, label, patch }) => (
            <Field
              key={field}
              id={`${id}-${field}`}
              label={label}
              error={fieldError(errors[field])}
            >
              {(control) => (
                <Input
                  {...control}
                  inputMode="decimal"
                  autoComplete="off"
                  value={form[field]}
                  onChange={(event) => onChange(patch(event.target.value))}
                  onBlur={onBlur}
                />
              )}
            </Field>
          ))}
          <div className="flex flex-col gap-2">
            <span className="text-sm leading-none font-medium">{t.position.ratio}</span>
            {ratio === null ? (
              <p className="text-xs text-muted-foreground">{t.position.ratioUnknown}</p>
            ) : (
              <p className="text-lg font-semibold tabular-nums">{t.position.ratioValue(ratio)}</p>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function NotesBlock({
  form,
  autosave,
  onChange,
  onBlur,
}: {
  form: EntryForm;
  autosave: Autosave;
  onChange: (patch: Partial<EntryForm>) => void;
  onBlur: () => void;
}) {
  const id = useId();
  const listId = `${id}-tags`;
  const [draft, setDraft] = useState('');
  const [rejection, setRejection] = useState<TagRejection | null>(null);
  const tags = useJournalTags();

  const commitTag = (raw: string) => {
    const result = addTag(form.tags, raw);
    setRejection(result.rejected);
    if (result.rejected === null) {
      onChange({ tags: result.tags });
      setDraft('');
    }
  };

  const removeTag = (name: string) => {
    setRejection(null);
    onChange({ tags: form.tags.filter((tag) => tag !== name) });
  };

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 p-5">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <h2 className="text-sm font-medium">{t.position.notesTitle}</h2>
          <SaveIndicator autosave={autosave} announce />
        </div>

        <Field id={`${id}-notes`} label={t.position.notesLabel}>
          {(control) => (
            <Textarea
              {...control}
              rows={5}
              maxLength={MAX_TEXT_LENGTH}
              placeholder={t.position.notesPlaceholder}
              value={form.notes}
              onChange={(event) => onChange({ notes: event.target.value })}
              onBlur={onBlur}
            />
          )}
        </Field>

        <Field
          id={`${id}-tag`}
          label={t.position.tagsLabel}
          hint={t.position.tagsHint}
          error={rejectionMessage(rejection)}
        >
          {(control) => (
            <div className="flex flex-col gap-2">
              {form.tags.length > 0 ? (
                <ul className="flex flex-wrap gap-1.5">
                  {form.tags.map((tag) => (
                    <li key={tag}>
                      <Badge className="gap-1 pr-1">
                        {tag}
                        <button
                          type="button"
                          aria-label={t.position.tagRemove(tag)}
                          className="rounded-full p-0.5 hover:bg-foreground/10"
                          onClick={() => removeTag(tag)}
                        >
                          <X className="size-3" aria-hidden="true" />
                        </button>
                      </Badge>
                    </li>
                  ))}
                </ul>
              ) : null}
              <div className="flex gap-2">
                <Input
                  {...control}
                  list={listId}
                  autoComplete="off"
                  maxLength={MAX_TAG_LENGTH}
                  placeholder={t.position.tagsPlaceholder}
                  value={draft}
                  onChange={(event) => {
                    setRejection(null);
                    setDraft(event.target.value);
                  }}
                  onKeyDown={(event) => {
                    // Enter внутри карточки не должен ничего отправлять, кроме тега.
                    if (event.key === 'Enter' || event.key === ',') {
                      event.preventDefault();
                      commitTag(draft);
                    }
                  }}
                  onBlur={onBlur}
                />
                <Button
                  type="button"
                  variant="outline"
                  disabled={draft.trim() === ''}
                  onClick={() => commitTag(draft)}
                >
                  {t.position.tagAdd}
                </Button>
              </div>
              <datalist id={listId}>
                {(tags.data?.items ?? []).map((tag) => (
                  <option key={tag.id} value={tag.name} />
                ))}
              </datalist>
            </div>
          )}
        </Field>
      </CardContent>
    </Card>
  );
}
