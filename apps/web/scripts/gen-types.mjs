/**
 * `make types` — OpenAPI живого API → src/api/schema.d.ts.
 *
 * Схема берётся у запущенного контейнера, а не из статического файла: файл в репозитории
 * пришлось бы обновлять руками, и он расходился бы с приложением молча. Профиль local
 * обязателен — только в нём объявлен /api/v1/dev/outbox (app/main.py), а страница писем
 * типизируется из той же схемы.
 */
import { mkdir, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import openapiTS, { astToString } from 'openapi-typescript';
import { format, resolveConfig } from 'prettier';

const WEB_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const OUTPUT = resolve(WEB_DIR, 'src/api/schema.d.ts');
const DEFAULT_URL = 'http://127.0.0.1:8000/api/v1/openapi.json';

const url = process.env.OPENAPI_URL ?? DEFAULT_URL;

async function readSchema() {
  let response;
  try {
    response = await fetch(url);
  } catch (cause) {
    throw new Error(
      `Схема недоступна по ${url}: ${cause.message}\n` +
        'Подними локальный стек: make up (или задай OPENAPI_URL).',
      { cause },
    );
  }
  if (!response.ok) {
    throw new Error(`Схема недоступна по ${url}: HTTP ${response.status}.`);
  }
  return response.json();
}

const schema = await readSchema();

if (!schema.paths?.['/api/v1/dev/outbox']) {
  // Схема без dev-маршрута снята с APP_ENV=prod. Типы страницы писем из неё не соберутся,
  // и падение на `npm run typecheck` объяснить было бы нечем.
  throw new Error(
    'В схеме нет /api/v1/dev/outbox — она снята не с профиля local. ' +
      'Проверь APP_ENV=local в .env и повтори.',
  );
}

const contents = astToString(await openapiTS(schema));
const prettierConfig = await resolveConfig(OUTPUT);
const formatted = await format(contents, { ...prettierConfig, filepath: OUTPUT });

await mkdir(dirname(OUTPUT), { recursive: true });
await writeFile(OUTPUT, formatted, 'utf8');

console.log(`Типы обновлены из ${url}: ${OUTPUT}`);
