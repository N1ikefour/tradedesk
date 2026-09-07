/**
 * Рефлексия: поля формы ⇄ тело `PUT /journal/positions/{id}/reflection`.
 *
 * ⚠️ Как и у записи журнала, тело собирается значением типа из схемы: обязательны все
 * поля (SPEC.md 5.4), поэтому забытое — ошибка компиляции. Пустое поле — это `null`
 * («не отвечал»), а не пропуск.
 *
 * `filled_at` считает сервер и только он: клиент не знает правил «первое сохранение с
 * хотя бы одним заполненным полем» и не должен их повторять.
 */
import type { ReflectionDetail, ReflectionUpdate, Vocab } from '@/journal/api';

export type Grade = NonNullable<ReflectionUpdate['setup_grade']>;
export type Emotion = NonNullable<ReflectionUpdate['emotion_before']>;
export type Mistake = ReflectionUpdate['mistakes'][number];

/**
 * Порядок показа — SPEC.md 3.5. Значения сверены со схемой через `satisfies`: опечатка в
 * ключе не доедет до экрана. Полноту набора стережёт другое место — словарь подписей в
 * `i18n` объявлен как `Record<Emotion, string>`, и новое значение в API ломает сборку.
 */
export const GRADES = ['A', 'B', 'C', 'D'] as const satisfies readonly Grade[];

export const EMOTIONS = [
  'calm',
  'focused',
  'edgy',
  'fomo',
  'frustrated',
  'bored',
  'euphoric',
  'fearful',
  'tired',
] as const satisfies readonly Emotion[];

export const MISTAKES = [
  'no_plan',
  'early_entry',
  'late_entry',
  'chased',
  'moved_sl',
  'no_sl',
  'oversized',
  'revenge',
  'early_exit',
  'held_too_long',
  'against_trend',
  'news_ignored',
  'overtrading',
] as const satisfies readonly Mistake[];

export const CONFIDENCE_VALUES = [1, 2, 3, 4, 5] as const;

export type ReflectionForm = {
  readonly setupGrade: Grade | null;
  readonly executionGrade: Grade | null;
  readonly followedPlan: boolean | null;
  readonly emotionBefore: Emotion | null;
  readonly emotionDuring: Emotion | null;
  readonly emotionAfter: Emotion | null;
  readonly mistakes: readonly Mistake[];
  readonly confidence: number | null;
  readonly freeText: string;
};

export const EMPTY_REFLECTION_FORM: ReflectionForm = {
  setupGrade: null,
  executionGrade: null,
  followedPlan: null,
  emotionBefore: null,
  emotionDuring: null,
  emotionAfter: null,
  mistakes: [],
  confidence: null,
  freeText: '',
};

function isGrade(value: string | null): value is Grade {
  return value !== null && (GRADES as readonly string[]).includes(value);
}

export function isEmotion(value: string | null): value is Emotion {
  return value !== null && (EMOTIONS as readonly string[]).includes(value);
}

export function isMistake(value: string): value is Mistake {
  return (MISTAKES as readonly string[]).includes(value);
}

/**
 * Ответ сервера → форма. Значение вне словаря отбрасывается: подписи у него нет, и в
 * карточке оно осталось бы пустым местом, которое нечем объяснить.
 */
export function reflectionFormFrom(reflection: ReflectionDetail | null): ReflectionForm {
  if (reflection === null) {
    return EMPTY_REFLECTION_FORM;
  }
  return {
    setupGrade: isGrade(reflection.setup_grade) ? reflection.setup_grade : null,
    executionGrade: isGrade(reflection.execution_grade) ? reflection.execution_grade : null,
    followedPlan: reflection.followed_plan,
    emotionBefore: isEmotion(reflection.emotion_before) ? reflection.emotion_before : null,
    emotionDuring: isEmotion(reflection.emotion_during) ? reflection.emotion_during : null,
    emotionAfter: isEmotion(reflection.emotion_after) ? reflection.emotion_after : null,
    mistakes: reflection.mistakes.filter(isMistake),
    confidence: reflection.confidence,
    freeText: reflection.free_text ?? '',
  };
}

export function reflectionBody(form: ReflectionForm): ReflectionUpdate {
  const freeText = form.freeText.trim();
  return {
    setup_grade: form.setupGrade,
    execution_grade: form.executionGrade,
    followed_plan: form.followedPlan,
    emotion_before: form.emotionBefore,
    emotion_during: form.emotionDuring,
    emotion_after: form.emotionAfter,
    mistakes: [...form.mistakes],
    confidence: form.confidence,
    free_text: freeText === '' ? null : freeText,
  };
}

/**
 * Что показывать в списках. Набор приходит с сервера (`GET /journal/vocab`, SPEC.md 3.5),
 * порядок — его же; неизвестные ключи выбрасываются, потому что послать их всё равно
 * нельзя. Пока словарь не приехал, показывается набор из схемы: форма обязана работать
 * с первой секунды, а не ждать второго запроса.
 */
export function vocabOptions(vocab: Vocab | undefined): {
  emotions: readonly Emotion[];
  mistakes: readonly Mistake[];
} {
  if (vocab === undefined) {
    return { emotions: EMOTIONS, mistakes: MISTAKES };
  }
  const emotions = vocab.emotions.filter(isEmotion);
  const mistakes = vocab.mistakes.filter(isMistake);
  return {
    emotions: emotions.length === 0 ? EMOTIONS : emotions,
    mistakes: mistakes.length === 0 ? MISTAKES : mistakes,
  };
}
