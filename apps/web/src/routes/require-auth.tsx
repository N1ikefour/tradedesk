import { Navigate, Outlet, useLocation } from 'react-router';

import { isServerUnreachable } from '@/api/errors';
import { useSession } from '@/auth/session';
import { FullScreenLoader, FullScreenNotice } from '@/components/full-screen-loader';
import { t } from '@/i18n';

/**
 * Гейт защищённых маршрутов. Пока состояние сессии неизвестно, рисуется загрузка:
 * отрисовать содержимое и потом увести на /login означало бы мигнуть чужим экраном.
 *
 * Различаются три положения дел, а не два (X-13, X-42). «Грузится» — запрос идёт.
 * «Приостановлено» — запрос стоит, потому что вкладка была в фоне, и сам он не сдвинется.
 * «Не отвечает» — приложение не поднято; для этой установки это штатный утренний путь, а
 * не край: человек включает компьютер и открывает страницу раньше, чем Docker Desktop
 * успевает поднять контейнеры (SETUP.md 8).
 *
 * Остальные неудачи запроса сессии — те, где сервер ответил, — уводят на /login:
 * оставаться на защищённой странице без подтверждённой сессии нельзя. Но «не смогли
 * проверить» и «не вошёл» разные вещи, поэтому причина передаётся дальше и /login её
 * объясняет.
 */
export function RequireAuth() {
  const session = useSession();
  const location = useLocation();
  const from = location.pathname + location.search;

  const retry = () => {
    void session.refetch();
  };

  // Раньше этот случай тоже уезжал на /login, и это был тупик: форма входа ходит на тот же
  // недоступный API, то есть человеку предлагали войти туда, куда нельзя достучаться.
  // Экран остаётся на месте — дождавшись Docker Desktop, человек нажимает «Повторить» и
  // попадает ровно туда, куда шёл; возврат во вкладку перезапрашивает сессию сам.
  if (session.isError && isServerUnreachable(session.error)) {
    return (
      <FullScreenNotice
        title={t.connection.serverDownTitle}
        hint={t.connection.serverDownHint}
        onRetry={retry}
        retryDisabled={session.isFetching}
      />
    );
  }

  if (session.isPending) {
    if (session.fetchStatus === 'paused') {
      return (
        <FullScreenNotice
          title={t.connection.pausedTitle}
          hint={t.connection.pausedHint}
          onRetry={retry}
          retryDisabled={session.isFetching}
        />
      );
    }
    return <FullScreenLoader />;
  }

  if (session.isError) {
    return <Navigate to="/login" replace state={{ from, reason: 'check-failed' }} />;
  }

  if (!session.data) {
    return <Navigate to="/login" replace state={{ from }} />;
  }

  return <Outlet />;
}
