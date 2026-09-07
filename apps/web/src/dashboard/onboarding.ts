/**
 * Шаги онбординга — SPEC.md 9.3, DoD `S2-10`: «новый пользователь видит шаги; после
 * подключения счёта галочки проставляются».
 *
 * Каждая галочка считается **по факту**, а не по нажатой кнопке и не по прошедшему
 * времени: счёт есть → коллектор выходил на связь → пришла хоть одна позиция → есть хоть
 * одна заполненная рефлексия. Поэтому шаг нельзя «пройти» мимо результата: пока сделки не
 * доехали, третья галочка не встанет, чем бы человек ни щёлкал.
 *
 * Сегодня это не редкий случай, а единственный реальный: `positions` наполняет ингест
 * (`S1-04`), которого ещё нет, — и первый человек увидит именно эти шаги.
 */
import type { Account } from '@/accounts/api';
import { usesCollector } from '@/accounts/status';
import { t } from '@/i18n';

export type OnboardingStepKey = 'account' | 'collector' | 'positions' | 'reflection';

export type OnboardingStep = {
  readonly key: OnboardingStepKey;
  readonly title: string;
  readonly hint: string;
  readonly done: boolean;
  readonly action: { readonly to: string; readonly label: string };
};

export type OnboardingFacts = {
  readonly accounts: readonly Account[];
  /** Есть ли хоть одна рефлексия с `filled_at` — ответ сервера, а не догадка. */
  readonly hasReflection: boolean;
};

/**
 * Шаг про коллектор показывается только тем, кому он нужен. Счёт «вручную» heartbeat не
 * пришлёт никогда, и вечная пустая галочка на нём означала бы поломку, которой нет.
 * Пока счетов нет вовсе, шаг остаётся: путь по умолчанию — MT5.
 */
function collectorApplies(accounts: readonly Account[]): boolean {
  return accounts.length === 0 || accounts.some(usesCollector);
}

export function buildOnboarding(facts: OnboardingFacts): readonly OnboardingStep[] {
  const { accounts, hasReflection } = facts;
  const steps: OnboardingStep[] = [
    {
      key: 'account',
      title: t.dashboard.stepAccountTitle,
      hint: t.dashboard.stepAccountHint,
      done: accounts.length > 0,
      action: { to: '/accounts', label: t.dashboard.stepAccountAction },
    },
  ];
  if (collectorApplies(accounts)) {
    steps.push({
      key: 'collector',
      title: t.dashboard.stepCollectorTitle,
      hint: t.dashboard.stepCollectorHint,
      done: accounts.some((account) => account.last_heartbeat_at !== null),
      action: { to: '/accounts', label: t.dashboard.stepCollectorAction },
    });
  }
  steps.push(
    {
      key: 'positions',
      title: t.dashboard.stepPositionsTitle,
      hint: t.dashboard.stepPositionsHint,
      done: accounts.some((account) => account.positions_count > 0),
      action: { to: '/accounts', label: t.dashboard.stepPositionsAction },
    },
    {
      key: 'reflection',
      title: t.dashboard.stepReflectionTitle,
      hint: t.dashboard.stepReflectionHint,
      done: hasReflection,
      action: { to: '/journal', label: t.dashboard.stepReflectionAction },
    },
  );
  return steps;
}

export function isOnboardingComplete(steps: readonly OnboardingStep[]): boolean {
  return steps.every((step) => step.done);
}

/** Первый невыполненный шаг — единственный, у которого показана кнопка действия. */
export function currentStep(steps: readonly OnboardingStep[]): OnboardingStepKey | null {
  return steps.find((step) => !step.done)?.key ?? null;
}
