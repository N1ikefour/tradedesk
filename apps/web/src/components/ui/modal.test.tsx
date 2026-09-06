import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Modal } from '@/components/ui/modal';
import { t } from '@/i18n';

/**
 * Хозяин окна написан так же, как настоящие вызывающие: `onClose` — стрелка, то есть
 * новая функция на каждый рендер. Ровно на этом окно и ломалось.
 */
function Host({ onClose = () => {} }: { onClose?: () => void }) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState('');

  return (
    <>
      <Button type="button" onClick={() => setOpen(true)}>
        Открыть
      </Button>
      <Modal
        open={open}
        onClose={() => {
          setOpen(false);
          onClose();
        }}
        title="Окно"
      >
        <label htmlFor="modal-field">Поле</label>
        <Input id="modal-field" value={value} onChange={(event) => setValue(event.target.value)} />
      </Modal>
    </>
  );
}

async function openModal(props: { onClose?: () => void } = {}) {
  const user = userEvent.setup();
  render(<Host {...props} />);
  await user.click(screen.getByRole('button', { name: 'Открыть' }));
  return user;
}

describe('Modal', () => {
  /**
   * Регрессия: эффект окна зависел от `onClose`, а тот менялся каждый рендер. Каждое
   * нажатие клавиши переигрывало эффект и уводило фокус на кнопку закрытия, поэтому в
   * поле оставался один символ, а пробел в тексте нажимал сфокусированную кнопку и
   * закрывал окно вместе с введённым.
   */
  it('поле принимает весь текст, включая пробелы, и окно не закрывается', async () => {
    const onClose = vi.fn();
    const user = await openModal({ onClose });

    const field = screen.getByLabelText('Поле');
    await user.type(field, 'FTMO Demo 42');

    expect(field).toHaveValue('FTMO Demo 42');
    expect(field).toHaveFocus();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });

  it('открывшись, забирает фокус внутрь себя', async () => {
    await openModal();

    expect(screen.getByRole('dialog')).toContainElement(document.activeElement as HTMLElement);
  });

  it('Escape закрывает окно', async () => {
    const onClose = vi.fn();
    const user = await openModal({ onClose });

    await user.keyboard('{Escape}');

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('кнопка закрытия закрывает окно и возвращает фокус вызвавшей кнопке', async () => {
    const user = await openModal();

    await user.click(screen.getByRole('button', { name: t.common.close }));

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Открыть' })).toHaveFocus();
  });
});
