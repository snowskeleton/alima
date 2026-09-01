import { Select } from '../ui/Select';
import { FEED_SORT_ORDER_OPTIONS, type FeedSortOrder } from '../../api/types';

interface FeedSortOrderSelectProps {
  /** Manual feeds can be hand-ordered; smart feeds have no positions to honour. */
  feedType: string;
  value: FeedSortOrder;
  onChange: (value: FeedSortOrder) => void;
}

export function FeedSortOrderSelect({ feedType, value, onChange }: FeedSortOrderSelectProps) {
  const options = FEED_SORT_ORDER_OPTIONS.filter(
    (o) => o.value !== 'manual' || feedType === 'manual'
  );

  return (
    <div className="space-y-1">
      <Select
        label="Episode Order"
        value={value}
        onChange={(e) => onChange(e.target.value as FeedSortOrder)}
        options={options}
      />
      <p className="text-xs text-gray-400">
        Podcast apps sort episodes by publication date, so any order other than purchase
        date publishes synthetic dates to keep your chosen order intact.
      </p>
    </div>
  );
}
