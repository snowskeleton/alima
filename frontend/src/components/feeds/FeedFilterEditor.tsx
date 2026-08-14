import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { Select } from '../ui/Select';

export interface FeedFilter {
  field: string;
  operator: string;
  value: string;
}

export const FILTER_FIELDS = [
  { value: 'author', label: 'Author' },
  { value: 'title', label: 'Title' },
  { value: 'series', label: 'Series' },
  { value: 'narrator', label: 'Narrator' },
  { value: 'publisher', label: 'Publisher' },
];

export const FILTER_OPERATORS = [
  { value: 'contains', label: 'contains' },
  { value: 'not_contains', label: 'does not contain' },
  { value: 'is', label: 'is exactly' },
  { value: 'is_not', label: 'is not' },
];

/**
 * Parse a feed's stored filter_criteria into filter rows, handling the legacy
 * single-filter format ({type, value}) the backend still accepts.
 */
export function parseFilterCriteria(criteria: Record<string, unknown> | null | undefined): FeedFilter[] {
  if (!criteria) return [];

  const raw = criteria.filters;
  if (Array.isArray(raw)) {
    return raw
      .map((f) => f as Partial<FeedFilter> & { type?: string })
      .map((f) => ({
        field: f.field ?? f.type ?? 'author',
        operator: f.operator ?? 'contains',
        value: f.value ?? '',
      }))
      .filter((f) => f.value !== '');
  }

  if (typeof criteria.type === 'string' && typeof criteria.value === 'string') {
    return [{ field: criteria.type, operator: 'contains', value: criteria.value }];
  }

  return [];
}

/** Serialize rows for the `filters_json` form field, dropping empty values. */
export function serializeFilters(filters: FeedFilter[]): string {
  return JSON.stringify(
    filters
      .map((f) => ({ ...f, value: f.value.trim() }))
      .filter((f) => f.value !== ''),
  );
}

interface FeedFilterEditorProps {
  filters: FeedFilter[];
  onChange: (filters: FeedFilter[]) => void;
}

export function FeedFilterEditor({ filters, onChange }: FeedFilterEditorProps) {
  const update = (index: number, patch: Partial<FeedFilter>) =>
    onChange(filters.map((f, i) => (i === index ? { ...f, ...patch } : f)));

  const remove = (index: number) => onChange(filters.filter((_, i) => i !== index));

  const add = () => onChange([...filters, { field: 'author', operator: 'contains', value: '' }]);

  return (
    <div className="space-y-3 p-3 bg-gray-50 rounded-lg border border-gray-200">
      <p className="text-xs text-gray-500">
        Smart feeds automatically include downloaded books matching all of these filters. Use
        &ldquo;does not contain&rdquo; or &ldquo;is not&rdquo; to exclude books. No filters means all books.
      </p>

      {filters.map((filter, i) => (
        <div key={i} className="flex flex-wrap items-end gap-2">
          <div className="w-32">
            <Select
              aria-label="Field"
              value={filter.field}
              onChange={(e) => update(i, { field: e.target.value })}
              options={FILTER_FIELDS}
            />
          </div>
          <div className="w-40">
            <Select
              aria-label="Operator"
              value={filter.operator}
              onChange={(e) => update(i, { operator: e.target.value })}
              options={FILTER_OPERATORS}
            />
          </div>
          <div className="flex-1 min-w-[10rem]">
            <Input
              aria-label="Value"
              value={filter.value}
              onChange={(e) => update(i, { value: e.target.value })}
              placeholder="e.g. Brandon Sanderson"
            />
          </div>
          <Button type="button" variant="danger" size="sm" onClick={() => remove(i)}>
            Remove
          </Button>
        </div>
      ))}

      <Button type="button" variant="secondary" size="sm" onClick={add}>
        + Add Filter
      </Button>
    </div>
  );
}
