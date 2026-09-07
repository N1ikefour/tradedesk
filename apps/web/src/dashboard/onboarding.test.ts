import { describe, expect, it } from 'vitest';

import type { Account } from '@/accounts/api';
import { buildOnboarding, currentStep, isOnboardingComplete } from '@/dashboard/onboarding';

function account(overrides: Partial<Account> = {}): Account {
  return {
    id: '0199a2b0-0000-7000-8000-0000000000a1',
    label: 'Демо A',
    is_demo: true,
    color: '#2563eb',
    platform: 'mt5',
    broker: null,
    server: 'Broker-Demo',
    login: 5_001_234,
    currency: 'USD',
    account_type: null,
    server_utc_offset_minutes: null,
    status: 'pending',
    status_message: null,
    last_sync_at: null,
    last_heartbeat_at: null,
    collector_id: null,
    sort_order: 0,
    created_at: '2026-09-01T10:00:00Z',
    positions_count: 0,
    ...overrides,
  };
}

function done(steps: readonly { key: string; done: boolean }[]): string[] {
  return steps.filter((step) => step.done).map((step) => step.key);
}

describe('шаги онбординга', () => {
  it('у нового пользователя не отмечено ничего', () => {
    const steps = buildOnboarding({ accounts: [], hasReflection: false });

    expect(steps.map((step) => step.key)).toEqual([
      'account',
      'collector',
      'positions',
      'reflection',
    ]);
    expect(done(steps)).toEqual([]);
    expect(currentStep(steps)).toBe('account');
    expect(isOnboardingComplete(steps)).toBe(false);
  });

  it('добавленный счёт отмечает первый шаг и переводит стрелку на второй', () => {
    const steps = buildOnboarding({ accounts: [account()], hasReflection: false });

    expect(done(steps)).toEqual(['account']);
    expect(currentStep(steps)).toBe('collector');
  });

  it('галочка коллектора встаёт по факту связи, а не по статусу счёта', () => {
    const steps = buildOnboarding({
      accounts: [account({ status: 'connected', last_heartbeat_at: '2026-09-07T10:00:00Z' })],
      hasReflection: false,
    });

    expect(done(steps)).toEqual(['account', 'collector']);
    // Позиций всё ещё нет: связь есть, сделок нет — это и показано.
    expect(currentStep(steps)).toBe('positions');
  });

  it('первая приехавшая позиция отмечает синк, первая рефлексия закрывает онбординг', () => {
    const connected = account({
      status: 'connected',
      last_heartbeat_at: '2026-09-07T10:00:00Z',
      positions_count: 12,
    });

    expect(done(buildOnboarding({ accounts: [connected], hasReflection: false }))).toEqual([
      'account',
      'collector',
      'positions',
    ]);
    const all = buildOnboarding({ accounts: [connected], hasReflection: true });
    expect(isOnboardingComplete(all)).toBe(true);
    expect(currentStep(all)).toBeNull();
  });

  it('счёт «вручную» не ждёт коллектора: шага про него нет', () => {
    const steps = buildOnboarding({
      accounts: [account({ platform: 'manual', server: null, login: null })],
      hasReflection: false,
    });

    expect(steps.map((step) => step.key)).toEqual(['account', 'positions', 'reflection']);
  });

  it('факты берутся по всем счетам, а не по первому', () => {
    const steps = buildOnboarding({
      accounts: [
        account({ id: '0199a2b0-0000-7000-8000-0000000000a1' }),
        account({
          id: '0199a2b0-0000-7000-8000-0000000000a2',
          last_heartbeat_at: '2026-09-07T10:00:00Z',
          positions_count: 3,
        }),
      ],
      hasReflection: false,
    });

    expect(done(steps)).toEqual(['account', 'collector', 'positions']);
  });
});
