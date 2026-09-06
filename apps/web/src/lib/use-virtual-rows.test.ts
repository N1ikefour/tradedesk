import { act, renderHook, type RenderHookResult } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { FALLBACK_VIEWPORT_HEIGHT, useVirtualRows, type VirtualRows } from '@/lib/use-virtual-rows';

/** Высота строки журнала и запас окна по умолчанию — те же числа, что в таблице. */
const ROW_HEIGHT = 45;
const OVERSCAN = 6;
const VIEWPORT = 450;
/** Сколько строк помещается в окно: `ceil(450 / 45)`. */
const VISIBLE = 10;
/** Длина окна с запасом сверху и снизу. */
const WINDOW = VISIBLE + OVERSCAN * 2;

/**
 * Кадры под управлением теста. Настоящий `requestAnimationFrame` в jsdom выполняется
 * когда захочет, а проверяется здесь именно схлопывание событий в один кадр — то есть
 * очередь, а не результат.
 */
function stubFrames() {
  let nextId = 1;
  const queue = new Map<number, FrameRequestCallback>();
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback): number => {
    const id = nextId;
    nextId += 1;
    queue.set(id, callback);
    return id;
  });
  vi.stubGlobal('cancelAnimationFrame', (id: number): void => {
    queue.delete(id);
  });
  return {
    get pending(): number {
      return queue.size;
    },
    run(): void {
      const callbacks = [...queue.values()];
      queue.clear();
      act(() => {
        for (const callback of callbacks) {
          callback(0);
        }
      });
    },
  };
}

/**
 * Контейнер прокрутки. В jsdom нет раскладки, поэтому и высота окна, и позиция
 * прокрутки задаются напрямую: без этого хук всегда считал бы окно от нуля.
 */
function scrollBox(height: number) {
  const node = document.createElement('div');
  let scrollTop = 0;
  Object.defineProperty(node, 'clientHeight', { configurable: true, value: height });
  Object.defineProperty(node, 'scrollTop', {
    configurable: true,
    get: () => scrollTop,
    set: (value: number) => {
      scrollTop = value;
    },
  });
  document.body.appendChild(node);
  return node;
}

function mount(
  count: number,
  node: HTMLElement,
): RenderHookResult<VirtualRows, unknown> & { scrollTo: (top: number) => void } {
  const containerRef = { current: node };
  const rendered = renderHook(() => useVirtualRows({ count, rowHeight: ROW_HEIGHT, containerRef }));
  return Object.assign(rendered, {
    scrollTo: (top: number) => {
      node.scrollTop = top;
      act(() => rendered.result.current.onScroll());
    },
  });
}

/** Инвариант виртуализации: окно и отступы всегда складываются в высоту всего списка. */
function totalHeight(window: VirtualRows): number {
  return window.paddingTop + (window.end - window.start) * ROW_HEIGHT + window.paddingBottom;
}

describe('useVirtualRows', () => {
  it('первый кадр — окно от начала списка, без отступа сверху', () => {
    stubFrames();
    const { result } = mount(1000, scrollBox(VIEWPORT));

    expect(result.current.start).toBe(0);
    expect(result.current.end).toBe(WINDOW);
    expect(result.current.paddingTop).toBe(0);
    expect(result.current.paddingBottom).toBe((1000 - WINDOW) * ROW_HEIGHT);
    expect(totalHeight(result.current)).toBe(1000 * ROW_HEIGHT);
  });

  it('прокрутка сдвигает окно, а высота списка от этого не меняется', () => {
    const frames = stubFrames();
    const { result, scrollTo } = mount(1000, scrollBox(VIEWPORT));

    scrollTo(100 * ROW_HEIGHT);
    // До кадра окно ещё старое: обновление стоит в очереди, а не применяется на событие.
    expect(result.current.start).toBe(0);
    frames.run();

    expect(result.current.start).toBe(100 - OVERSCAN);
    expect(result.current.end).toBe(100 - OVERSCAN + WINDOW);
    expect(result.current.paddingTop).toBe((100 - OVERSCAN) * ROW_HEIGHT);
    expect(totalHeight(result.current)).toBe(1000 * ROW_HEIGHT);
  });

  it('прокрутка до конца упирается в последнюю строку и не даёт отступа снизу', () => {
    const frames = stubFrames();
    const { result, scrollTo } = mount(1000, scrollBox(VIEWPORT));

    scrollTo(1000 * ROW_HEIGHT);
    frames.run();

    expect(result.current.end).toBe(1000);
    expect(result.current.paddingBottom).toBe(0);
    expect(totalHeight(result.current)).toBe(1000 * ROW_HEIGHT);
  });

  it('события за один кадр схлопываются: их приходит больше, чем кадров', () => {
    const frames = stubFrames();
    const { result, scrollTo } = mount(1000, scrollBox(VIEWPORT));

    act(() => {
      result.current.onScroll();
      result.current.onScroll();
      result.current.onScroll();
    });

    expect(frames.pending).toBe(1);

    frames.run();
    // Кадр отдал слот обратно, иначе следующая прокрутка осталась бы без обновления.
    scrollTo(10 * ROW_HEIGHT);
    expect(frames.pending).toBe(1);
  });

  it('уход вкладки не оставляет кадр занятым навсегда', () => {
    const frames = stubFrames();
    const { result, scrollTo } = mount(1000, scrollBox(VIEWPORT));

    scrollTo(50 * ROW_HEIGHT);
    expect(frames.pending).toBe(1);

    // В скрытой вкладке кадр не выполняется. Если слот не освободить, все последующие
    // события прокрутки уходят в ранний выход и окно замирает после возвращения.
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });

    expect(frames.pending).toBe(0);
    expect(result.current.start).toBe(50 - OVERSCAN);

    scrollTo(80 * ROW_HEIGHT);
    frames.run();

    expect(result.current.start).toBe(80 - OVERSCAN);
  });

  it('изменение размера окна перезамеряет контейнер', () => {
    stubFrames();
    const node = scrollBox(VIEWPORT);
    const { result } = mount(1000, node);

    expect(result.current.end).toBe(WINDOW);

    Object.defineProperty(node, 'clientHeight', { configurable: true, value: VIEWPORT * 2 });
    act(() => {
      window.dispatchEvent(new Event('resize'));
    });

    expect(result.current.end).toBe(VISIBLE * 2 + OVERSCAN * 2);
  });

  it('список короче окна показывается целиком', () => {
    stubFrames();
    const { result } = mount(3, scrollBox(VIEWPORT));

    expect(result.current.start).toBe(0);
    expect(result.current.end).toBe(3);
    expect(result.current.paddingTop).toBe(0);
    expect(result.current.paddingBottom).toBe(0);
  });

  it('прокрутка мимо конца короткого списка не уводит окно за него', () => {
    const frames = stubFrames();
    const { result, scrollTo } = mount(3, scrollBox(VIEWPORT));

    // Так бывает, когда список ужался под фильтр, а контейнер ещё прокручен вниз.
    scrollTo(100 * ROW_HEIGHT);
    frames.run();

    expect(result.current.start).toBe(2);
    expect(result.current.end).toBe(3);
    expect(result.current.paddingBottom).toBe(0);
    expect(totalHeight(result.current)).toBe(3 * ROW_HEIGHT);
  });

  it('пустой список не даёт ни строк, ни отступов', () => {
    stubFrames();
    const { result } = mount(0, scrollBox(VIEWPORT));

    expect(result.current).toMatchObject({ start: 0, end: 0, paddingTop: 0, paddingBottom: 0 });
  });

  it('неизмеримое окно берёт запасную высоту, а не показывает пустоту', () => {
    stubFrames();
    const { result } = mount(1000, scrollBox(0));

    expect(result.current.end).toBe(
      Math.ceil(FALLBACK_VIEWPORT_HEIGHT / ROW_HEIGHT) + OVERSCAN * 2,
    );
  });
});
