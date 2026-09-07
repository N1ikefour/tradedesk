/**
 * Шаги онбординга — SPEC.md 9.3 и DoD `S2-10`. Сегодня это самое частое состояние экрана:
 * позиций в базе нет ни у кого, потому что ингест (`S1-04`) не написан, — и первое, что
 * человек увидит после входа, должно объяснять, что делать дальше, а не выглядеть
 * поломкой.
 *
 * Кнопка показана только у ближайшего невыполненного шага: четыре кнопки подряд не
 * говорят, с какой начать.
 */
import { Check } from 'lucide-react';
import { Link } from 'react-router';

import { DashboardBlock } from '@/dashboard/block';
import { currentStep, type OnboardingStep } from '@/dashboard/onboarding';
import { Button } from '@/components/ui/button';
import { t } from '@/i18n';
import { cn } from '@/lib/utils';

export function OnboardingBlock({ steps }: { steps: readonly OnboardingStep[] }) {
  const next = currentStep(steps);

  return (
    <DashboardBlock title={t.dashboard.onboardingTitle} hint={t.dashboard.onboardingHint}>
      <ol className="flex flex-col gap-3">
        {steps.map((step) => (
          <li key={step.key} className="flex items-start gap-3">
            <span
              className={cn(
                'mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border',
                step.done
                  ? 'border-success/40 bg-success/10 text-success'
                  : 'border-border text-muted-foreground',
              )}
            >
              {step.done ? <Check className="size-3" aria-hidden="true" /> : null}
              <span className="sr-only">
                {step.done ? t.dashboard.onboardingDone : t.dashboard.onboardingPending}
              </span>
            </span>
            <span className="flex min-w-0 flex-col items-start gap-1">
              <span className={cn('text-sm', step.done ? 'text-muted-foreground' : 'font-medium')}>
                {step.title}
              </span>
              {step.done ? null : (
                <span className="text-xs text-muted-foreground">{step.hint}</span>
              )}
              {step.key === next ? (
                <Button type="button" variant="outline" size="sm" asChild>
                  <Link to={step.action.to}>{step.action.label}</Link>
                </Button>
              ) : null}
            </span>
          </li>
        ))}
      </ol>
    </DashboardBlock>
  );
}
