import { t } from '@/i18n';

/**
 * Экран ожидания. Показывается, пока неизвестно, вошёл ли пользователь: без него
 * защищённая страница успевала бы мигнуть до редиректа на /login.
 */
export function FullScreenLoader() {
  return (
    <div
      className="flex h-full min-h-screen items-center justify-center text-sm text-muted-foreground"
      role="status"
    >
      {t.common.loading}
    </div>
  );
}
