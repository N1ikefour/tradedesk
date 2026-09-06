/**
 * Панель фильтров журнала — SPEC.md 9.3.
 *
 * Текстовые поля держат свой ввод и применяются по Enter или кнопкой, а не на каждое
 * нажатие: каждое применение — это запись в адрес и запрос к серверу, и посимвольный
 * поиск превратил бы набор слова в десять запросов и десять записей в историю браузера.
 * Списки и кнопки периода применяются сразу — вместе с тем, что уже набрано в полях,
 * чтобы на экране не оставалось введённого, но не применённого.
 */
import { ArrowDownWideNarrow, ArrowUpNarrowWide } from 'lucide-react';
import { useEffect, useState, type FormEvent } from 'react';

import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { t } from '@/i18n';
import {
  DEFAULT_FILTERS,
  DIRECTION_VALUES,
  REFLECTION_VALUES,
  RESULT_VALUES,
  SORT_FIELDS,
  STATUS_VALUES,
  oneOf,
  type JournalFilters,
  type SortField,
} from '@/journal/filters';
import { formatDateTime } from '@/lib/format';
import { PERIOD_PRESETS, type PeriodPreset } from '@/lib/trading-day';

const PERIOD_LABELS: Record<PeriodPreset, string> = {
  today: t.journal.periodToday,
  week: t.journal.periodWeek,
  month: t.journal.periodMonth,
  all: t.journal.periodAll,
};

const SORT_LABELS: Record<SortField, string> = {
  close_time: t.journal.sortFieldCloseTime,
  open_time: t.journal.sortFieldOpenTime,
  net_pnl: t.journal.sortFieldNetPnl,
  symbol_norm: t.journal.sortFieldSymbolNorm,
  duration_seconds: t.journal.sortFieldDurationSeconds,
};

const TAG_SEPARATOR = ',';

function splitTags(raw: string): string[] {
  const seen = new Set<string>();
  for (const part of raw.split(TAG_SEPARATOR)) {
    const tag = part.trim();
    if (tag !== '') {
      seen.add(tag);
    }
  }
  return [...seen];
}

export function FiltersPanel({
  filters,
  timeZone,
  onChange,
}: {
  filters: JournalFilters;
  timeZone: string;
  onChange: (next: JournalFilters) => void;
}) {
  const [symbol, setSymbol] = useState(filters.symbol);
  const [tags, setTags] = useState(filters.tags.join(`${TAG_SEPARATOR} `));
  const [q, setQ] = useState(filters.q);

  // Фильтры могут смениться мимо панели: кнопкой «Сбросить», ссылкой из другого экрана,
  // кнопкой «назад» браузера. Поля обязаны показать то, что применено на самом деле.
  useEffect(() => {
    setSymbol(filters.symbol);
    setTags(filters.tags.join(`${TAG_SEPARATOR} `));
    setQ(filters.q);
  }, [filters]);

  const commit = (patch: Partial<JournalFilters>) => {
    onChange({ ...filters, symbol, tags: splitTags(tags), q, ...patch });
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    commit({});
  };

  const setPeriod = (period: PeriodPreset) => {
    commit({ period, from: null, to: null });
  };

  return (
    <form
      onSubmit={submit}
      aria-label={t.journal.filtersTitle}
      className="flex flex-col gap-4 rounded-lg border border-border p-4"
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">{t.journal.periodLabel}</span>
        {PERIOD_PRESETS.map((preset) => (
          <Button
            key={preset}
            type="button"
            size="sm"
            variant={filters.period === preset ? 'default' : 'outline'}
            aria-pressed={filters.period === preset}
            onClick={() => setPeriod(preset)}
          >
            {PERIOD_LABELS[preset]}
          </Button>
        ))}
        {filters.period === 'custom' ? (
          <span className="flex items-center gap-2 rounded-md border border-border px-2 py-1 text-sm">
            <span>
              {t.journal.periodCustom}
              {filters.from === null
                ? ''
                : ` ${t.journal.periodCustomFrom(formatDateTime(filters.from, timeZone))}`}
              {filters.to === null
                ? ''
                : ` ${t.journal.periodCustomTo(formatDateTime(filters.to, timeZone))}`}
            </span>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="h-6 px-2"
              onClick={() => setPeriod('all')}
            >
              {t.journal.periodCustomClear}
            </Button>
          </span>
        ) : null}
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Field id="journal-symbol" label={t.journal.symbolLabel} hint={t.journal.symbolHint}>
          {(props) => (
            <Input
              {...props}
              value={symbol}
              placeholder={t.journal.symbolPlaceholder}
              onChange={(event) => setSymbol(event.target.value)}
              onBlur={() => commit({})}
            />
          )}
        </Field>

        <Field id="journal-search" label={t.journal.searchLabel}>
          {(props) => (
            <Input
              {...props}
              value={q}
              placeholder={t.journal.searchPlaceholder}
              onChange={(event) => setQ(event.target.value)}
              onBlur={() => commit({})}
            />
          )}
        </Field>

        <Field id="journal-tags" label={t.journal.tagsLabel} hint={t.journal.tagsHint}>
          {(props) => (
            <Input
              {...props}
              value={tags}
              placeholder={t.journal.tagsPlaceholder}
              onChange={(event) => setTags(event.target.value)}
              onBlur={() => commit({})}
            />
          )}
        </Field>

        <Field id="journal-status" label={t.journal.statusLabel}>
          {(props) => (
            <Select
              {...props}
              value={filters.status ?? ''}
              onChange={(event) => commit({ status: oneOf(event.target.value, STATUS_VALUES) })}
            >
              <option value="">{t.journal.statusAny}</option>
              <option value="open">{t.journal.statusOpen}</option>
              <option value="closed">{t.journal.statusClosed}</option>
            </Select>
          )}
        </Field>

        <Field id="journal-direction" label={t.journal.directionLabel}>
          {(props) => (
            <Select
              {...props}
              value={filters.direction ?? ''}
              onChange={(event) =>
                commit({ direction: oneOf(event.target.value, DIRECTION_VALUES) })
              }
            >
              <option value="">{t.journal.directionAny}</option>
              <option value="long">{t.journal.long}</option>
              <option value="short">{t.journal.short}</option>
            </Select>
          )}
        </Field>

        <Field id="journal-result" label={t.journal.resultLabel}>
          {(props) => (
            <Select
              {...props}
              value={filters.result ?? ''}
              onChange={(event) => commit({ result: oneOf(event.target.value, RESULT_VALUES) })}
            >
              <option value="">{t.journal.resultAny}</option>
              <option value="win">{t.journal.resultWin}</option>
              <option value="loss">{t.journal.resultLoss}</option>
              {/* Пункт появляется, только если значение уже выбрано: чужая ссылка с
                  `result=be` иначе показывала бы список, отфильтрованный неизвестно чем. */}
              {filters.result === 'be' ? (
                <option value="be">{t.journal.resultBreakeven}</option>
              ) : null}
            </Select>
          )}
        </Field>

        <Field id="journal-reflection" label={t.journal.reflectionLabel}>
          {(props) => (
            <Select
              {...props}
              value={filters.reflection ?? ''}
              onChange={(event) =>
                commit({ reflection: oneOf(event.target.value, REFLECTION_VALUES) })
              }
            >
              <option value="">{t.journal.reflectionAny}</option>
              <option value="filled">{t.journal.reflectionFilled}</option>
              <option value="none">{t.journal.reflectionNone}</option>
            </Select>
          )}
        </Field>

        <div className="flex flex-col gap-2">
          <Label htmlFor="journal-sort">{t.journal.sortLabel}</Label>
          <div className="flex gap-2">
            <Select
              id="journal-sort"
              value={filters.sortField}
              onChange={(event) =>
                commit({ sortField: oneOf(event.target.value, SORT_FIELDS) ?? filters.sortField })
              }
            >
              {SORT_FIELDS.map((field) => (
                <option key={field} value={field}>
                  {SORT_LABELS[field]}
                </option>
              ))}
            </Select>
            <Button
              type="button"
              variant="outline"
              size="icon"
              className="shrink-0"
              aria-label={t.journal.sortToggle}
              title={filters.sortDirection === 'asc' ? t.journal.sortAsc : t.journal.sortDesc}
              onClick={() =>
                commit({ sortDirection: filters.sortDirection === 'asc' ? 'desc' : 'asc' })
              }
            >
              {filters.sortDirection === 'asc' ? (
                <ArrowUpNarrowWide aria-hidden="true" />
              ) : (
                <ArrowDownWideNarrow aria-hidden="true" />
              )}
            </Button>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <Button type="submit" size="sm">
          {t.journal.apply}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={() => {
            setSymbol(DEFAULT_FILTERS.symbol);
            setTags('');
            setQ(DEFAULT_FILTERS.q);
            onChange(DEFAULT_FILTERS);
          }}
        >
          {t.journal.resetFilters}
        </Button>
      </div>
    </form>
  );
}
