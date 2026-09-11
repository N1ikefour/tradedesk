/**
 * Блок «Коллектор» (SPEC.md 9.3) — единственное место в приложении, где написано, что
 * коллектор такое и что произойдёт, когда он замолчит. Правдивость текста тестом не
 * проверяется: это сверка с кодом сервера, и делается она глазами. Проверяются три
 * свойства, которые текст уже терял, — каждое ловится мутацией одной строки `ru.ts`.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { CollectorBlock } from '@/accounts/collector-block';
import { t } from '@/i18n';

/** Так выглядят наши тикеты: `S1-10`, `X-25`, `T-01`. Человеку они не значат ничего. */
const TICKET_ID = /\b[A-Z]\d?-\d{2}\b/;

/**
 * Порог «коллектор не на связи» живёт на сервере (`COLLECTOR_OFFLINE_AFTER`) и на фронт
 * не копируется — решение `S1-11`, SPEC.md 9.3. Число, вписанное в текст, четвёртой
 * копией разошлось бы с остальными молча.
 *
 * Граница слова здесь своя (`\p{L}` под флагом `u`), а не `\b`: тот считает словом
 * только ASCII и в русской фразе не срабатывает вовсе.
 */
const THRESHOLD = /(?<![\p{L}\d])(5|пят[ьи])\s+мин/iu;

/**
 * Текст, который сервер пишет в `status_message`, когда `check_collectors` уводит счёт
 * в `needs_attention` (`accounts.service.COLLECTOR_OFFLINE_MESSAGE`). Блок обязан
 * называть его дословно: человек ищет на экране ровно эти слова.
 */
const OFFLINE_MESSAGE = 'Коллектор не на связи';

function blockText(): string {
  const { container } = render(<CollectorBlock />);
  return container.textContent ?? '';
}

describe('блок «Коллектор»', () => {
  it('показывает все абзацы: объяснение, установку, поведение статуса и оговорку', () => {
    render(<CollectorBlock />);

    expect(screen.getByText(t.accounts.collectorTitle)).toBeInTheDocument();
    expect(screen.getByText(t.accounts.collectorHint)).toBeInTheDocument();
    expect(screen.getByText(t.accounts.collectorSetup)).toBeInTheDocument();
    expect(screen.getByText(t.accounts.collectorStaleNote)).toBeInTheDocument();
    expect(screen.getByText(t.accounts.collectorNotReady)).toBeInTheDocument();
  });

  /**
   * Развилка `T-07`: пароля в форме больше нет, и вместо него человек обязан прочитать, как
   * счёт вообще попадает в синк и почему синкается только открытый. Место одно — правило
   * общее для всех счетов; следствие для одного счёта стоит на его карточке.
   */
  it('называет словами, что коллектор подключается к открытому терминалу, и цену этого', () => {
    const text = blockText();

    expect(text).toContain(t.accounts.collectorOpenTerminal);
    expect(text).toContain(t.accounts.collectorOneAtATime);
  });

  it('не называет внутренних номеров задач', () => {
    expect(blockText()).not.toMatch(TICKET_ID);
  });

  it('не заводит своей копии порога «не на связи»', () => {
    expect(blockText()).not.toMatch(THRESHOLD);
  });

  it('называет статус и причину теми же словами, что появятся на карточке счёта', () => {
    const text = blockText();

    expect(text).toContain(t.accounts.statusNeedsAttention);
    expect(text).toContain(OFFLINE_MESSAGE);
  });
});
