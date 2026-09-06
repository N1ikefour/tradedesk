import { act, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { useSyncedForm } from '@/journal/use-synced-form';

type Form = { readonly text: string };

/**
 * Три правила хука разнонаправлены, и каждое ловится только своим сценарием: перечитанную
 * запись форма обязана подхватить, набранное — отстоять, а собственное эхо — принять.
 * Упростить условие до одного из них можно, не уронив соседние тесты, — поэтому здесь их
 * три.
 */
function Harness({ server }: { server: Form }) {
  const { form, setForm, markSent } = useSyncedForm(server);
  return (
    <div>
      <input
        aria-label="поле"
        value={form.text}
        onChange={(event) => setForm({ text: event.target.value })}
      />
      <button type="button" onClick={markSent}>
        отправлено
      </button>
    </div>
  );
}

function field(): HTMLInputElement {
  return screen.getByLabelText('поле');
}

function type(value: string): void {
  act(() => {
    const input = field();
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
    setter?.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
}

describe('форма с источником на сервере', () => {
  it('нетронутая форма догоняет перечитанную запись', () => {
    // Иначе автосохранение записало бы старое поверх нового: форма, оставшаяся с прежними
    // значениями, считается изменённой и уходит в PUT.
    const view = render(<Harness server={{ text: 'из базы' }} />);

    view.rerender(<Harness server={{ text: 'из соседней вкладки' }} />);

    expect(field().value).toBe('из соседней вкладки');
  });

  it('набранное побеждает перечитанную запись', () => {
    const view = render(<Harness server={{ text: 'из базы' }} />);

    type('моя мысль');
    view.rerender(<Harness server={{ text: 'из соседней вкладки' }} />);

    // Перезаписать поле, в котором человек прямо сейчас пишет, нельзя ничем.
    expect(field().value).toBe('моя мысль');
  });

  it('ответ на собственное сохранение принимается: написание задаёт сервер', () => {
    const view = render(<Harness server={{ text: '' }} />);

    type('trend');
    act(() => {
      screen.getByRole('button', { name: 'отправлено' }).click();
    });
    view.rerender(<Harness server={{ text: 'Trend' }} />);

    // Не принять эхо — значит считать форму изменённой навсегда и слать PUT по кругу.
    expect(field().value).toBe('Trend');
  });
});
