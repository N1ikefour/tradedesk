/**
 * Где введённый секрет может пережить запрос. Разметка — только одно из мест и самое
 * обманчивое: значение поля живёт в свойстве `value`, а `innerHTML` показывает атрибут,
 * поэтому проверка «нет в разметке» проходит и над полем, в котором пароль остался.
 * Тело запроса живёт третьей копией — в кэше мутаций, и оттуда достижимо через дерево
 * компонентов до `QueryClient`.
 */
import type { QueryClient } from '@tanstack/react-query';

function safeStringify(value: unknown): string {
  try {
    return JSON.stringify(value) ?? '';
  } catch {
    return '';
  }
}

/** Места, где секрет найден. Пустой список — секрета на странице нет. */
export function findSecret(secret: string, client: QueryClient): string[] {
  const places: string[] = [];

  if (document.body.innerHTML.includes(secret)) {
    places.push('разметка');
  }

  const fields = document.querySelectorAll<HTMLInputElement | HTMLTextAreaElement>(
    'input, textarea',
  );
  for (const field of fields) {
    if (field.value.includes(secret)) {
      places.push(`значение поля ${field.id === '' ? field.type : field.id}`);
    }
  }

  const mutations = client.getMutationCache().getAll();
  if (mutations.some((mutation) => safeStringify(mutation.state).includes(secret))) {
    places.push('кэш мутаций');
  }

  const queries = client.getQueryCache().getAll();
  if (queries.some((query) => safeStringify(query.state.data).includes(secret))) {
    places.push('кэш запросов');
  }

  if (window.location.href.includes(secret)) {
    places.push('адрес');
  }
  if (safeStringify({ ...localStorage }).includes(secret)) {
    places.push('localStorage');
  }
  if (safeStringify({ ...sessionStorage }).includes(secret)) {
    places.push('sessionStorage');
  }

  return places;
}
