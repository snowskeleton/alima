import { Input } from '../ui/Input';
import { Select } from '../ui/Select';

interface BookFiltersProps {
  search: string;
  onSearchChange: (v: string) => void;
  status: string;
  onStatusChange: (v: string) => void;
  source: string;
  onSourceChange: (v: string) => void;
  seriesFilter: string;
  onSeriesFilterChange: (v: string) => void;
  sort: string;
  onSortChange: (v: string) => void;
  order: string;
  onOrderChange: (v: string) => void;
  view: string;
  onViewChange: (v: string) => void;
}

export function BookFilters({
  search, onSearchChange,
  status, onStatusChange,
  source, onSourceChange,
  seriesFilter, onSeriesFilterChange,
  sort, onSortChange,
  order, onOrderChange,
  view, onViewChange,
}: BookFiltersProps) {
  return (
    <div className="flex flex-wrap items-end gap-3 mb-4">
      <div className="flex-1 min-w-[200px]">
        <Input
          placeholder="Search books..."
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
        />
      </div>
      <Select
        value={status}
        onChange={(e) => onStatusChange(e.target.value)}
        options={[
          { value: '', label: 'All Status' },
          { value: 'downloaded', label: 'Downloaded' },
          { value: 'pending', label: 'Pending' },
          { value: 'disabled', label: 'Disabled' },
          { value: 'unavailable', label: 'Unavailable' },
        ]}
      />
      <Select
        value={source}
        onChange={(e) => onSourceChange(e.target.value)}
        options={[
          { value: '', label: 'All Sources' },
          { value: 'audible', label: 'Audible' },
          { value: 'imported', label: 'Imported' },
        ]}
      />
      <Select
        value={seriesFilter}
        onChange={(e) => onSeriesFilterChange(e.target.value)}
        options={[
          { value: '', label: 'Series/Standalone' },
          { value: 'series', label: 'Has Series' },
          { value: 'standalone', label: 'Standalone' },
        ]}
      />
      <Select
        value={sort}
        onChange={(e) => onSortChange(e.target.value)}
        options={[
          { value: 'added_at', label: 'Date Added' },
          { value: 'title', label: 'Title' },
          { value: 'author', label: 'Author' },
          { value: 'downloaded_at', label: 'Downloaded' },
        ]}
      />
      <Select
        value={order}
        onChange={(e) => onOrderChange(e.target.value)}
        options={[
          { value: 'desc', label: 'Newest' },
          { value: 'asc', label: 'Oldest' },
        ]}
      />
      <Select
        value={view}
        onChange={(e) => onViewChange(e.target.value)}
        options={[
          { value: 'grid', label: 'Grid' },
          { value: 'list', label: 'List' },
          { value: 'compact', label: 'Compact' },
        ]}
      />
    </div>
  );
}
