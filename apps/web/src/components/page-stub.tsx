import { t } from '@/i18n';

/**
 * Заглушка маршрута из SPEC.md 9.1. Задача S0-07 делает проверяемыми роутер и layout;
 * содержимое экранов приезжает своими задачами этапов 1–2.
 */
export function PageStub({ title }: { title: string }) {
  return (
    <section className="flex flex-col gap-2">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      <p className="text-sm text-muted-foreground">{t.stub.note}</p>
    </section>
  );
}
