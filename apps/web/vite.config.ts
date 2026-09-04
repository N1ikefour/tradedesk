import { fileURLToPath, URL } from 'node:url';

import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// Куда dev-сервер проксирует /api. В docker-compose это api:8000 (переменная приходит
// из compose), при запуске `npm run dev` на хосте — опубликованный порт api.
const apiTarget = process.env.VITE_API_TARGET ?? 'http://localhost:8000';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': {
        target: apiTarget,
        // changeOrigin: false — Host и Origin остаются браузерными, иначе проверка Origin
        // в API (SPEC.md 4) отклоняет каждый мутирующий запрос как чужой источник.
        changeOrigin: false,
        // xfwd: без него API видит адрес vite вместо адреса браузера, и лимит
        // «10 запросов кода в час на IP» становится общим на всю установку (X-06).
        xfwd: true,
      },
    },
  },
});
