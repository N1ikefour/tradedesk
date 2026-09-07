/**
 * Блок «Рефлексия» — SPEC.md 9.3: две строки оценок A/B/C/D, «по плану», три селекта
 * эмоций, чипы ошибок, уверенность 1–5, текст. Автосохранение с задержкой 800 мс.
 *
 * Раскладка подчинена одному числу из DoD: рефлексия заполняется за 30 секунд. Замер по
 * секундомеру дал 11 с, но это **механика** — дотянуться до каждого контрола и набрать
 * текст в темпе печати, без единой паузы на подумать. Значит на то, ради чего рефлексию
 * и заполняют — вспомнить сделку и сформулировать мысль, — форма оставляет ~19 с, и
 * каждое лишнее нажатие ест именно их. Поэтому всё, что выбирается, выбирается одним
 * нажатием и лежит на виду, а не в выпадающих списках; свободный текст — единственное
 * поле, где надо печатать.
 *
 * Селекты эмоций нативные, а иконка стоит рядом с полем: `<select>` не умеет рисовать
 * значок внутри пункта, а свой список ради этого стоил бы клавиатуры и поиска с
 * клавиатуры, которые у нативного уже есть.
 */
import { useCallback, useId, useMemo, type ReactNode } from 'react';

import {
  BatteryLow,
  Brain,
  CircleDashed,
  Coffee,
  Flame,
  Gauge,
  Ghost,
  Rocket,
  Waves,
  Zap,
  type LucideIcon,
} from 'lucide-react';

import { Card, CardContent } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { t } from '@/i18n';
import {
  useSaveReflection,
  useVocab,
  type PositionCard,
  type ReflectionUpdate,
} from '@/journal/api';
import {
  CONFIDENCE_VALUES,
  GRADES,
  isEmotion,
  reflectionBody,
  reflectionFormFrom,
  vocabOptions,
  type Emotion,
  type Grade,
  type Mistake,
  type ReflectionForm,
} from '@/journal/reflection-form';
import { SaveIndicator } from '@/journal/save-indicator';
import { useAutosave, useFlushOnUnmount } from '@/journal/use-autosave';
import { useSyncedForm } from '@/journal/use-synced-form';
import { MAX_TEXT_LENGTH } from '@/journal/entry-form';
import { formatDateTime } from '@/lib/format';
import { cn } from '@/lib/utils';
import { useProfileTimeZone } from '@/user/profile';

/**
 * Подписи объявлены как полный словарь перечисления: значение, добавленное в API, ломает
 * сборку здесь, а не появляется на экране голым ключом.
 */
const EMOTION_LABELS: Record<Emotion, string> = t.position.emotions;
const MISTAKE_LABELS: Record<Mistake, string> = t.position.mistakeLabels;
const EMOTION_ICONS: Record<Emotion, LucideIcon> = {
  calm: Waves,
  focused: Brain,
  edgy: Zap,
  fomo: Rocket,
  frustrated: Flame,
  bored: Coffee,
  euphoric: Gauge,
  fearful: Ghost,
  tired: BatteryLow,
};

function Choice({
  pressed,
  onClick,
  label,
  children,
}: {
  pressed: boolean;
  onClick: () => void;
  label?: string;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      aria-label={label}
      onClick={onClick}
      className={cn(
        'inline-flex h-9 min-w-9 items-center justify-center rounded-md border px-3 text-sm',
        'transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring',
        pressed
          ? 'border-primary bg-primary text-primary-foreground'
          : 'border-input bg-background hover:bg-accent hover:text-accent-foreground',
      )}
    >
      {children}
    </button>
  );
}

function Group({ label, children }: { label: string; children: ReactNode }) {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-2 text-sm leading-none font-medium">{label}</legend>
      <div className="flex flex-wrap gap-1.5">{children}</div>
    </fieldset>
  );
}

export function ReflectionBlock({
  position,
  onTouched,
}: {
  position: PositionCard;
  onTouched: () => void;
}) {
  const id = useId();
  const timeZone = useProfileTimeZone();
  const reflection = position.reflection;
  const serverForm = useMemo(() => reflectionFormFrom(reflection), [reflection]);
  const savedBody = useMemo(() => reflectionBody(serverForm), [serverForm]);

  const { form, setForm, markSent } = useSyncedForm(serverForm);

  const { mutateAsync } = useSaveReflection(position.id);
  const save = useCallback(
    (body: ReflectionUpdate) => {
      markSent();
      return mutateAsync(body);
    },
    [markSent, mutateAsync],
  );

  const body = useMemo(() => reflectionBody(form), [form]);
  const autosave = useAutosave({ body, savedBody, save });
  useFlushOnUnmount(autosave, onTouched);

  const vocab = useVocab();
  const options = useMemo(() => vocabOptions(vocab.data), [vocab.data]);

  const update = (patch: Partial<ReflectionForm>) => {
    setForm((current) => ({ ...current, ...patch }));
  };

  /** Повторное нажатие снимает выбор: «не отвечал» — такое же состояние, как ответ. */
  const toggleGrade = (field: 'setupGrade' | 'executionGrade', grade: Grade) => {
    const next = form[field] === grade ? null : grade;
    update(field === 'setupGrade' ? { setupGrade: next } : { executionGrade: next });
  };

  const emotions: readonly {
    field: 'emotionBefore' | 'emotionDuring' | 'emotionAfter';
    label: string;
    patch: (value: Emotion | null) => Partial<ReflectionForm>;
  }[] = [
    {
      field: 'emotionBefore',
      label: t.position.emotionBefore,
      patch: (value) => ({ emotionBefore: value }),
    },
    {
      field: 'emotionDuring',
      label: t.position.emotionDuring,
      patch: (value) => ({ emotionDuring: value }),
    },
    {
      field: 'emotionAfter',
      label: t.position.emotionAfter,
      patch: (value) => ({ emotionAfter: value }),
    },
  ];

  return (
    <Card>
      <CardContent className="flex flex-col gap-5 p-5">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="flex flex-col gap-1">
            <h2 className="text-sm font-medium">{t.position.reflectionTitle}</h2>
            <p className="text-xs text-muted-foreground">
              {t.position.reflectionHint}
              {/* `filled_at` ставит сервер: «когда разобрал» это не «когда трогал». */}
              {reflection?.filled_at != null
                ? ` · ${t.position.reflectionFilledAt(formatDateTime(reflection.filled_at, timeZone))}`
                : ''}
            </p>
          </div>
          <SaveIndicator autosave={autosave} announce />
        </div>

        <div className="flex flex-wrap gap-x-8 gap-y-4">
          <Group label={t.position.setupGrade}>
            {GRADES.map((grade) => (
              <Choice
                key={grade}
                pressed={form.setupGrade === grade}
                label={t.position.gradeOption(t.position.setupGrade, grade)}
                onClick={() => toggleGrade('setupGrade', grade)}
              >
                {grade}
              </Choice>
            ))}
          </Group>

          <Group label={t.position.executionGrade}>
            {GRADES.map((grade) => (
              <Choice
                key={grade}
                pressed={form.executionGrade === grade}
                label={t.position.gradeOption(t.position.executionGrade, grade)}
                onClick={() => toggleGrade('executionGrade', grade)}
              >
                {grade}
              </Choice>
            ))}
          </Group>

          <Group label={t.position.followedPlan}>
            <Choice
              pressed={form.followedPlan === true}
              onClick={() => update({ followedPlan: form.followedPlan === true ? null : true })}
            >
              {t.position.followedPlanYes}
            </Choice>
            <Choice
              pressed={form.followedPlan === false}
              onClick={() => update({ followedPlan: form.followedPlan === false ? null : false })}
            >
              {t.position.followedPlanNo}
            </Choice>
          </Group>

          <Group label={t.position.confidence}>
            {CONFIDENCE_VALUES.map((value) => (
              <Choice
                key={value}
                pressed={form.confidence === value}
                label={t.position.confidenceOption(value)}
                onClick={() => update({ confidence: form.confidence === value ? null : value })}
              >
                {value}
              </Choice>
            ))}
          </Group>
        </div>

        <div className="grid gap-4 sm:grid-cols-3">
          {emotions.map(({ field, label, patch }) => {
            const value = form[field];
            const Icon = value === null ? CircleDashed : EMOTION_ICONS[value];
            return (
              <div key={field} className="flex flex-col gap-2">
                <Label htmlFor={`${id}-${field}`}>{label}</Label>
                <div className="flex items-center gap-2">
                  <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                  <Select
                    id={`${id}-${field}`}
                    value={value ?? ''}
                    onChange={(event) => {
                      const next = event.target.value;
                      patchEmotion(patch, next, update);
                    }}
                  >
                    <option value="">{t.position.emotionEmpty}</option>
                    {options.emotions.map((emotion) => (
                      <option key={emotion} value={emotion}>
                        {EMOTION_LABELS[emotion]}
                      </option>
                    ))}
                  </Select>
                </div>
              </div>
            );
          })}
        </div>

        <Group label={t.position.mistakes}>
          {options.mistakes.map((mistake) => (
            <Choice
              key={mistake}
              pressed={form.mistakes.includes(mistake)}
              onClick={() =>
                update({
                  mistakes: form.mistakes.includes(mistake)
                    ? form.mistakes.filter((value) => value !== mistake)
                    : [...form.mistakes, mistake],
                })
              }
            >
              {MISTAKE_LABELS[mistake]}
            </Choice>
          ))}
        </Group>

        <div className="flex flex-col gap-2">
          <Label htmlFor={`${id}-free-text`}>{t.position.freeText}</Label>
          <Textarea
            id={`${id}-free-text`}
            rows={4}
            maxLength={MAX_TEXT_LENGTH}
            placeholder={t.position.freeTextPlaceholder}
            value={form.freeText}
            onChange={(event) => update({ freeText: event.target.value })}
            onBlur={() => {
              void autosave.flush();
            }}
          />
        </div>
      </CardContent>
    </Card>
  );
}

/** Значение `<select>` — строка: в форму оно попадает только пройдя словарь. */
function patchEmotion(
  patch: (value: Emotion | null) => Partial<ReflectionForm>,
  raw: string,
  update: (patch: Partial<ReflectionForm>) => void,
): void {
  update(patch(isEmotion(raw) ? raw : null));
}
