/**
 * Спрятать и вернуть вкладку — настоящим событием, а не флагом `focusManager.setFocused`.
 * Менеджер фокуса спрашивает `document.visibilityState` и слушает `visibilitychange` на
 * окне, и только этот путь проходит целиком: приём из `S0-07`, записан в X-13 как
 * единственный способ воспроизвести паузу повторов в тесте.
 */
export function setTabHidden(hidden: boolean): void {
  Object.defineProperty(document, 'visibilityState', {
    value: hidden ? 'hidden' : 'visible',
    configurable: true,
  });
  document.dispatchEvent(new Event('visibilitychange', { bubbles: true }));
}
