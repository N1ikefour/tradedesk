import { Navigate, Outlet, useLocation } from 'react-router';

import { useSession } from '@/auth/session';
import { FullScreenLoader } from '@/components/full-screen-loader';

/**
 * Гейт защищённых маршрутов. Пока состояние сессии неизвестно, рисуется загрузка:
 * отрисовать содержимое и потом увести на /login означало бы мигнуть чужим экраном.
 * Ошибка запроса приравнивается к «не вошёл» — оставаться на защищённой странице
 * без подтверждённой сессии нельзя.
 */
export function RequireAuth() {
  const session = useSession();
  const location = useLocation();

  if (session.isPending) {
    return <FullScreenLoader />;
  }

  if (!session.data) {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }

  return <Outlet />;
}
