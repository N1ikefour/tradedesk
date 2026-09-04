import { Navigate, Outlet, useLocation } from 'react-router';

import { useSession } from '@/auth/session';
import { FullScreenLoader } from '@/components/full-screen-loader';

/**
 * Гейт защищённых маршрутов. Пока состояние сессии неизвестно, рисуется загрузка:
 * отрисовать содержимое и потом увести на /login означало бы мигнуть чужим экраном.
 *
 * Неудачный запрос сессии тоже уводит на /login — оставаться на защищённой странице
 * без подтверждённой сессии нельзя. Но «не смогли проверить» и «не вошёл» — разные вещи,
 * поэтому причина передаётся дальше и /login её объясняет.
 */
export function RequireAuth() {
  const session = useSession();
  const location = useLocation();
  const from = location.pathname + location.search;

  if (session.isPending) {
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
