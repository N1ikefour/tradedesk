import { act, fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AUTOSAVE_DELAY_MS, useAutosave } from '@/journal/use-autosave';

type Body = { readonly text: string };

/**
 * Форма в миниатюре: поле, тело из него и «сервер», который принимает тело. Хранилище
 * обновляется только успешным ответом — ровно как кэш запроса в карточке позиции.
 */
function Harness({ save }: { save: (body: Body) => Promise<unknown> }) {
  const [text, setText] = useState('');
  const [saved, setSaved] = useState('');
  const autosave = useAutosave<Body>({
    body: { text },
    savedBody: { text: saved },
    save: async (body) => {
      const result = await save(body);
      setSaved(body.text);
      return result;
    },
  });

  return (
    <div>
      <input
        aria-label="поле"
        value={text}
        onChange={(event) => setText(event.target.value)}
        onBlur={() => {
          void autosave.flush();
        }}
      />
      <output>{autosave.state}</output>
      <button type="button" onClick={autosave.retry}>
        повторить
      </button>
    </div>
  );
}

/** То же, но ответ сервера в форму не возвращается: «сохранённое» состояние не меняется. */
function HarnessWithoutEcho({ save }: { save: (body: Body) => Promise<unknown> }) {
  const [text, setText] = useState('');
  const autosave = useAutosave<Body>({ body: { text }, savedBody: { text: '' }, save });
  return (
    <div>
      <input
        aria-label="поле"
        value={text}
        onChange={(event) => setText(event.target.value)}
        onBlur={() => {
          void autosave.flush();
        }}
      />
      <output>{autosave.state}</output>
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

async function tick(ms: number): Promise<void> {
  await act(async () => {
    vi.advanceTimersByTime(ms);
  });
}

afterEach(() => {
  vi.useRealTimers();
});

describe('автосохранение', () => {
  it('ждёт паузу в 800 мс и отправляет последнее состояние, а не каждое нажатие', async () => {
    vi.useFakeTimers();
    const save = vi.fn().mockResolvedValue(undefined);
    render(<Harness save={save} />);

    type('пе');
    await tick(400);
    type('перв');
    await tick(400);
    expect(save).not.toHaveBeenCalled();

    await tick(AUTOSAVE_DELAY_MS);
    expect(save).toHaveBeenCalledTimes(1);
    expect(save).toHaveBeenCalledWith({ text: 'перв' });
    expect(screen.getByRole('status').textContent).toBe('saved');
  });

  it('совпавшее с сервером состояние не отправляется вовсе', async () => {
    vi.useFakeTimers();
    const save = vi.fn().mockResolvedValue(undefined);
    render(<Harness save={save} />);

    type('а');
    await tick(AUTOSAVE_DELAY_MS + 100);
    expect(save).toHaveBeenCalledTimes(1);

    // Ответ принят, форма и сервер снова совпали — второй запрос слать нечего.
    await tick(5_000);
    expect(save).toHaveBeenCalledTimes(1);
  });

  it('провал сети не теряет ввод и не превращается в бесконечные попытки', async () => {
    vi.useFakeTimers();
    const save = vi.fn().mockRejectedValue(new Error('сети нет'));
    render(<Harness save={save} />);

    type('важная мысль');
    await tick(AUTOSAVE_DELAY_MS + 100);

    expect(save).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('status').textContent).toBe('failed');
    // Главное: набранное осталось в поле, а не заменилось состоянием сервера.
    expect(field().value).toBe('важная мысль');

    await tick(10_000);
    expect(save).toHaveBeenCalledTimes(1);
  });

  it('после провала повтор отправляет то же тело, а правка снимает запрет сама', async () => {
    vi.useFakeTimers();
    const save = vi.fn().mockRejectedValueOnce(new Error('сети нет')).mockResolvedValue(undefined);
    render(<Harness save={save} />);

    type('текст');
    await tick(AUTOSAVE_DELAY_MS + 100);
    expect(screen.getByRole('status').textContent).toBe('failed');

    await act(async () => {
      screen.getByRole('button', { name: 'повторить' }).click();
    });
    expect(save).toHaveBeenCalledTimes(2);
    expect(save).toHaveBeenLastCalledWith({ text: 'текст' });
    expect(screen.getByRole('status').textContent).toBe('saved');
  });

  it('дозапись на выходе не повторяет тело, которое уже доехало', async () => {
    vi.useFakeTimers();
    // «Сервер», который принял запись, но чей ответ до формы уже не дойдёт: ровно то, что
    // происходит при закрытии карточки — компонент снимается раньше ответа.
    const save = vi.fn().mockResolvedValue(undefined);
    render(<HarnessWithoutEcho save={save} />);

    type('одна правка');
    await tick(AUTOSAVE_DELAY_MS + 100);
    expect(save).toHaveBeenCalledTimes(1);

    await act(async () => {
      fireEvent.blur(field());
    });
    expect(save).toHaveBeenCalledTimes(1);
  });

  it('уход с поля сохраняет сразу, не дожидаясь задержки', async () => {
    vi.useFakeTimers();
    const save = vi.fn().mockResolvedValue(undefined);
    render(<Harness save={save} />);

    type('быстро');
    await act(async () => {
      fireEvent.blur(field());
    });

    expect(save).toHaveBeenCalledTimes(1);
    expect(save).toHaveBeenCalledWith({ text: 'быстро' });
  });
});
