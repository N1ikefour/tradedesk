import { RouterProvider, createBrowserRouter } from 'react-router';

import { AppProviders, createQueryClient } from '@/app-providers';
import { routes } from '@/routes/routes';

const queryClient = createQueryClient();
const router = createBrowserRouter(routes);

export function App() {
  return (
    <AppProviders client={queryClient}>
      <RouterProvider router={router} />
    </AppProviders>
  );
}
