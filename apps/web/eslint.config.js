import js from '@eslint/js';
import globals from 'globals';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  {
    ignores: [
      'dist',
      'node_modules',
      'playwright-report',
      'test-results',
      // Генерируется целью `make types` из живой схемы OpenAPI — правится не здесь.
      'src/api/schema.d.ts',
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: globals.browser,
    },
    rules: {
      '@typescript-eslint/no-explicit-any': 'error',
      'no-restricted-syntax': [
        'error',
        {
          // Комбинатор `>` обязателен: без него `:has()` видит `type` у вложенного JSX
          // внутри значения чужого атрибута (`title={<Icon type="warn" />}`) и кнопка
          // без типа проходит молча. `asChild` исключён: Slot рендерит ребёнка,
          // и `<button>` в DOM не появляется — тип там осел бы на чужом теге.
          selector:
            'JSXOpeningElement[name.name=/^(button|Button)$/]' +
            ':not(:has(> JSXAttribute[name.name="type"]))' +
            ':not(:has(> JSXAttribute[name.name="asChild"]))',
          message:
            'Кнопка без явного type по стандарту HTML равна type="submit": внутри <form> ' +
            'клик по ней и Enter в любом поле отправят форму — запросом, которого никто ' +
            'не просил. Укажи type="button" для действия на странице или type="submit", ' +
            'если кнопка действительно отправляет форму.',
        },
      ],
    },
  },
  {
    files: ['vite.config.ts', 'eslint.config.js', 'playwright.config.ts', 'scripts/**/*.mjs'],
    languageOptions: {
      globals: globals.node,
    },
  },
  {
    files: ['vitest.setup.ts', 'src/**/*.test.{ts,tsx}', 'src/test/**/*.{ts,tsx}', 'e2e/**/*.ts'],
    languageOptions: {
      globals: { ...globals.browser, ...globals.node },
    },
  },
);
