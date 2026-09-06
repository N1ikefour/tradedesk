/**
 * Окно видимых строк длинного списка (SPEC.md 9.3 — «таблица виртуализированная»).
 *
 * Список журнала догружается страницами и не имеет верхней границы: у активного трейдера
 * это тысячи позиций за год. Отрисованные разом, они превращают прокрутку в слайд-шоу —
 * не из-за React, а потому что браузер считает раскладку по всем строкам сразу.
 *
 * Реализация своя, хотя `@tanstack/react-virtual` разрешён `SPEC.md` 2.3 наравне с
 * `zustand`, — запрета на него нет. Причина в объёме задачи: строки здесь одной высоты и
 * не измеряются поштучно, поэтому всё поведение сводится к трём числам — с какой строки
 * начать, какой отступ поставить сверху и какой снизу. Библиотека решает задачу шире
 * (переменная высота, замер элементов, горизонтальные окна, динамические окна), и на
 * этом наборе даёт не меньше кода, а другой. Перевод на неё — отдельный разговор с
 * отдельным тикетом, а не то, что здесь запрещено.
 *
 * Высота строки — константа, и это ограничение названо честно: строка с переносом текста
 * сломала бы расчёт. Поэтому в таблице журнала ячейки не переносятся.
 */
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type RefObject } from 'react';

/**
 * Высота окна, пока настоящую измерить нечем: контейнер ещё не в документе, или движок
 * вовсе не считает раскладку (jsdom в тестах). Ноль дал бы пустой список без единой
 * строки — то есть пустой экран вместо журнала.
 */
export const FALLBACK_VIEWPORT_HEIGHT = 640;

export type VirtualRows = {
  /** Индекс первой отрисовываемой строки. */
  readonly start: number;
  /** Индекс за последней отрисовываемой строкой. */
  readonly end: number;
  readonly paddingTop: number;
  readonly paddingBottom: number;
  readonly onScroll: () => void;
};

export function useVirtualRows({
  count,
  rowHeight,
  overscan = 6,
  containerRef,
}: {
  count: number;
  rowHeight: number;
  overscan?: number;
  containerRef: RefObject<HTMLElement | null>;
}): VirtualRows {
  const [scrollTop, setScrollTop] = useState(0);
  const [viewport, setViewport] = useState(FALLBACK_VIEWPORT_HEIGHT);
  const frame = useRef<number | null>(null);

  useLayoutEffect(() => {
    const node = containerRef.current;
    if (node === null) {
      return;
    }
    const measure = () => {
      const height = node.clientHeight;
      setViewport(height > 0 ? height : FALLBACK_VIEWPORT_HEIGHT);
    };
    measure();
    window.addEventListener('resize', measure);
    return () => window.removeEventListener('resize', measure);
  }, [containerRef]);

  useEffect(
    () => () => {
      if (frame.current !== null) {
        window.cancelAnimationFrame(frame.current);
      }
    },
    [],
  );

  const applyScroll = useCallback(() => {
    const node = containerRef.current;
    if (node !== null) {
      setScrollTop(node.scrollTop);
    }
  }, [containerRef]);

  /**
   * Событий прокрутки приходит больше, чем кадров, и каждое из них — это перерисовка
   * окна. Обновление кладётся на кадр: лишние события за тот же кадр схлопываются.
   */
  const onScroll = useCallback(() => {
    if (frame.current !== null) {
      return;
    }
    frame.current = window.requestAnimationFrame(() => {
      frame.current = null;
      applyScroll();
    });
  }, [applyScroll]);

  useEffect(() => {
    // В скрытой вкладке кадры не выполняются, и запрошенный повисает вместе с ними:
    // слот занят, а значит каждое следующее событие прокрутки уходит в ранний выход.
    // Смена видимости закрывает кадр руками и применяет то, ради чего он ставился.
    const release = () => {
      if (frame.current === null) {
        return;
      }
      window.cancelAnimationFrame(frame.current);
      frame.current = null;
      applyScroll();
    };
    document.addEventListener('visibilitychange', release);
    return () => document.removeEventListener('visibilitychange', release);
  }, [applyScroll]);

  const visible = Math.ceil(viewport / rowHeight);
  const first = Math.max(0, Math.floor(scrollTop / rowHeight) - overscan);
  const start = Math.min(first, Math.max(0, count - 1));
  const end = Math.min(count, start + visible + overscan * 2);

  return {
    start,
    end,
    paddingTop: start * rowHeight,
    paddingBottom: Math.max(0, (count - end) * rowHeight),
    onScroll,
  };
}
