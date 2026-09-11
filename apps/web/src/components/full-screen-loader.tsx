import { Button } from '@/components/ui/button';
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

/**
 * Тот же экран, когда ждать молча нельзя: сервер не ответил или проверка приостановлена.
 * До входа под гейтом нет ни шапки, ни страницы — значит объяснение и кнопка обязаны быть
 * здесь, иначе единственный доступный человеку ход это F5, который ничего не меняет.
 */
export function FullScreenNotice({
  title,
  hint,
  onRetry,
  retryDisabled,
}: {
  title: string;
  hint: string;
  onRetry: () => void;
  retryDisabled: boolean;
}) {
  return (
    <div
      className="flex h-full min-h-screen flex-col items-center justify-center gap-3 px-4 text-center"
      role="status"
    >
      <p className="text-base font-medium">{title}</p>
      <p className="max-w-md text-sm text-muted-foreground">{hint}</p>
      <Button type="button" variant="outline" size="sm" disabled={retryDisabled} onClick={onRetry}>
        {t.common.retry}
      </Button>
    </div>
  );
}
