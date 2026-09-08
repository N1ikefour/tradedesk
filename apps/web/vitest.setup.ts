import '@testing-library/jest-dom/vitest';

import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

import { setUnauthorizedHandler } from '@/api/client';

afterEach(() => {
  cleanup();
  // Клиент API — модульный синглтон: обработчик 401 от предыдущего теста иначе
  // остался бы зарегистрированным и трогал чужой QueryClient.
  setUnauthorizedHandler(null);
  // Хранилище окна тоже общее на весь файл: незаконченная попытка входа из предыдущего
  // теста иначе поднимала бы следующий сразу на шаге ввода кода.
  window.sessionStorage.clear();
});
