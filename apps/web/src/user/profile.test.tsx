import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { AppProviders, createQueryClient } from '@/app-providers';
import { SESSION_QUERY_KEY } from '@/auth/session';
import { installFetchMock, jsonResponse } from '@/test/fetch-mock';
import { TEST_USER } from '@/test/render';
import { useDisplayTimeZone, useProfileTimeZone } from '@/user/profile';

/**
 * Зона машины подменена намеренно: иначе тест «без сессии показываем часы компьютера»
 * зависел бы от того, где стоит машина, и на компьютере в Екатеринбурге ничего бы
 * не проверял.
 */
const MACHINE_TIME_ZONE = 'Pacific/Kiritimati';

vi.mock('@/lib/time-zones', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/time-zones')>()),
  browserTimeZone: () => MACHINE_TIME_ZONE,
}));

const SESSION = 'GET /api/v1/auth/me';

function harness() {
  const client = createQueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <AppProviders client={client}>{children}</AppProviders>
  );
  return { client, wrapper };
}

describe('useDisplayTimeZone', () => {
  it('без сессии в кэше показывает зону компьютера и не запрашивает профиль', async () => {
    const { calls } = installFetchMock({ [SESSION]: () => jsonResponse(200, TEST_USER) });
    const { wrapper } = harness();

    const { result } = renderHook(() => useDisplayTimeZone(), { wrapper });

    expect(result.current).toBe(MACHINE_TIME_ZONE);
    // `/dev/outbox` открыт до входа: запрос профиля ради оформления дат там лишний.
    await waitFor(() => {
      expect(calls).toHaveLength(0);
    });
  });

  it('с сессией в кэше показывает зону профиля', () => {
    installFetchMock({ [SESSION]: () => jsonResponse(200, TEST_USER) });
    const { client, wrapper } = harness();
    client.setQueryData(SESSION_QUERY_KEY, TEST_USER);

    const { result } = renderHook(() => useDisplayTimeZone(), { wrapper });

    expect(result.current).toBe(TEST_USER.timezone);
  });
});

describe('useProfileTimeZone', () => {
  it('берёт зону из сессии', async () => {
    installFetchMock({ [SESSION]: () => jsonResponse(200, TEST_USER) });
    const { wrapper } = harness();

    const { result } = renderHook(() => useProfileTimeZone(), { wrapper });

    await waitFor(() => {
      expect(result.current).toBe(TEST_USER.timezone);
    });
  });

  it('зона, незнакомая движку, не роняет форматирование', async () => {
    const alien = { ...TEST_USER, timezone: 'Mars/Olympus' };
    installFetchMock({ [SESSION]: () => jsonResponse(200, alien) });
    const { client, wrapper } = harness();
    client.setQueryData(SESSION_QUERY_KEY, alien);

    const { result } = renderHook(() => useProfileTimeZone(), { wrapper });

    expect(result.current).toBe(MACHINE_TIME_ZONE);
  });
});
