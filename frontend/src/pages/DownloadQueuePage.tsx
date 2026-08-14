import { useEffect, useState } from 'react';
import { useDownloads, useDownloadActions } from '../api/hooks/useDownloads';
import { useJob } from '../api/hooks/useJobs';
import { PageSpinner } from '../components/ui/Spinner';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Input } from '../components/ui/Input';
import { Select } from '../components/ui/Select';
import { EmptyState } from '../components/ui/EmptyState';
import { Alert } from '../components/ui/Alert';
import { formatFileSize, formatDuration, timeAgo } from '../utils/format';

// Keys match the API, which serialises the enum's value (lowercase).
const statusColors: Record<string, 'gray' | 'green' | 'red' | 'yellow' | 'blue'> = {
  pending: 'gray',
  downloading: 'blue',
  decrypting: 'blue',
  completed: 'green',
  failed: 'red',
};

// 'stalled' is a server-side pseudo-status: in flight, but nothing is working
// on it any more. It has no enum member, only a per-entry flag.
const statusOptions = [
  { value: '', label: 'All statuses' },
  { value: 'pending', label: 'Pending' },
  { value: 'downloading', label: 'Downloading' },
  { value: 'decrypting', label: 'Decrypting' },
  { value: 'completed', label: 'Completed' },
  { value: 'failed', label: 'Failed' },
  { value: 'stalled', label: 'Stuck / stalled' },
];

/**
 * Shows that the page is refreshing itself, so a queue that isn't moving reads
 * as "nothing is happening" rather than "this page is stale again".
 */
function LiveIndicator({ isFetching, updatedAt }: { isFetching: boolean; updatedAt: number }) {
  // Re-render on a timer so "updated 40s ago" keeps counting up between polls.
  const [, tick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => tick((n) => n + 1), 5000);
    return () => clearInterval(id);
  }, []);

  const seconds = updatedAt ? Math.round((Date.now() - updatedAt) / 1000) : null;

  return (
    <span className="flex items-center gap-1.5 text-xs text-gray-500" title="This page updates on its own">
      <span
        className={`h-1.5 w-1.5 rounded-full ${
          isFetching ? 'bg-green-500 animate-pulse' : 'bg-green-500/50'
        }`}
      />
      {isFetching ? 'Updating…' : seconds !== null && seconds < 10 ? 'Live' : `Updated ${seconds}s ago`}
    </span>
  );
}

export function DownloadQueuePage() {
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [readStatus, setReadStatus] = useState('unread');
  const [account, setAccount] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [sort, setSort] = useState('created_at');
  const [order, setOrder] = useState('desc');
  const [selected, setSelected] = useState<number[]>([]);
  const [processJobId, setProcessJobId] = useState<number>();

  const { data, isLoading, isFetching, dataUpdatedAt } = useDownloads({ search, status, read_status: readStatus, account, date_from: dateFrom, date_to: dateTo, sort, order });
  const { retry, remove, patch, bulk, reapStale, processQueue } = useDownloadActions();
  const { data: job } = useJob(processJobId);

  // Only block on the very first load. Re-rendering the spinner on later
  // fetches would unmount the filter inputs and steal focus mid-typing.
  if (isLoading && !data) return <PageSpinner />;

  const entries = data?.entries ?? [];
  const stats = data?.stats;

  const toggleSelect = (id: number) => {
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  const selectAll = () => {
    if (selected.length === entries.length) {
      setSelected([]);
    } else {
      setSelected(entries.map((e) => e.id));
    }
  };

  const handleProcess = async () => {
    const result = await processQueue.mutateAsync();
    setProcessJobId(result.job_id);
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold text-gray-900">Download Queue</h1>
          <LiveIndicator isFetching={isFetching} updatedAt={dataUpdatedAt} />
        </div>
        <div className="flex items-center gap-2">
          <Button onClick={handleProcess} disabled={processQueue.isPending}>
            {processQueue.isPending ? 'Starting...' : 'Process Queue'}
          </Button>
        </div>
      </div>

      {job && job.status === 'running' && (
        <Alert type="info" className="mb-4">
          Processing downloads... {job.progress}/{job.total}
        </Alert>
      )}
      {job && job.status === 'completed' && (
        <Alert type="success" className="mb-4">
          Queue processing completed.
        </Alert>
      )}
      {job && job.status === 'failed' && (
        <Alert type="error" className="mb-4">
          Queue processing failed: {job.error_message}
        </Alert>
      )}

      {!!stats?.stalled && (
        <Alert type="warning" className="mb-4">
          <div className="flex items-center justify-between gap-3">
            <span>
              {stats.stalled} download{stats.stalled === 1 ? ' is' : 's are'} stuck with no
              worker behind {stats.stalled === 1 ? 'it' : 'them'}. They are re-queued
              automatically, or you can do it now.
            </span>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => reapStale.mutate()}
              disabled={reapStale.isPending}
            >
              {reapStale.isPending ? 'Re-queuing…' : 'Re-queue stuck'}
            </Button>
          </div>
        </Alert>
      )}

      {stats && (
        <div className="grid grid-cols-5 gap-3 mb-6">
          <div className="bg-white p-3 rounded-lg border border-gray-200 text-center">
            <div className="text-2xl font-bold text-gray-900">{stats.total}</div>
            <div className="text-xs text-gray-500">Total</div>
          </div>
          <div className="bg-white p-3 rounded-lg border border-gray-200 text-center">
            <div className="text-2xl font-bold text-gray-500">{stats.pending}</div>
            <div className="text-xs text-gray-500">Pending</div>
          </div>
          <div className="bg-white p-3 rounded-lg border border-gray-200 text-center">
            <div className="text-2xl font-bold text-blue-600">{stats.in_flight}</div>
            <div className="text-xs text-gray-500">In progress</div>
          </div>
          <div className="bg-white p-3 rounded-lg border border-gray-200 text-center">
            <div className="text-2xl font-bold text-green-600">{stats.completed}</div>
            <div className="text-xs text-gray-500">Completed</div>
          </div>
          <div className="bg-white p-3 rounded-lg border border-gray-200 text-center">
            <div className="text-2xl font-bold text-red-600">{stats.failed}</div>
            <div className="text-xs text-gray-500">Failed</div>
          </div>
        </div>
      )}

      <div className="bg-white p-4 rounded-lg border border-gray-200 mb-4">
        <div className="flex flex-wrap gap-3">
          <Input placeholder="Search…" value={search} onChange={(e) => setSearch(e.target.value)} className="w-44" />
          <Input placeholder="Account…" value={account} onChange={(e) => setAccount(e.target.value)} className="w-36" />
          <Select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            options={statusOptions}
          />
          <Select
            value={readStatus}
            onChange={(e) => setReadStatus(e.target.value)}
            options={[
              { value: '', label: 'All' },
              { value: 'unread', label: 'Unread' },
              { value: 'read', label: 'Read' },
            ]}
          />
          <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
            className="border border-gray-300 rounded-lg px-2 py-1.5 text-sm" title="From date" />
          <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
            className="border border-gray-300 rounded-lg px-2 py-1.5 text-sm" title="To date" />
          <Select
            value={sort}
            onChange={(e) => setSort(e.target.value)}
            options={[
              { value: 'created_at', label: 'Created' },
              { value: 'priority', label: 'Priority' },
              { value: 'status', label: 'Status' },
            ]}
          />
          <Button variant="ghost" size="sm" onClick={() => setOrder(order === 'desc' ? 'asc' : 'desc')}>
            {order === 'desc' ? 'Newest first' : 'Oldest first'}
          </Button>
        </div>
      </div>

      {selected.length > 0 && (
        <div className="bg-indigo-50 p-3 rounded-lg border border-indigo-200 mb-4 flex items-center gap-3">
          <span className="text-sm text-indigo-700">{selected.length} selected</span>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => bulk.mutate({ action: 'mark_read', entry_ids: selected }, { onSuccess: () => setSelected([]) })}
          >
            Mark Read
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => bulk.mutate({ action: 'mark_unread', entry_ids: selected }, { onSuccess: () => setSelected([]) })}
          >
            Mark Unread
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => bulk.mutate({ action: 'retry', entry_ids: selected }, { onSuccess: () => setSelected([]) })}
          >
            Re-queue
          </Button>
          <Button
            variant="danger"
            size="sm"
            onClick={() => {
              if (confirm(`Remove ${selected.length} entries?`)) {
                bulk.mutate({ action: 'remove', entry_ids: selected }, { onSuccess: () => setSelected([]) });
              }
            }}
          >
            Remove
          </Button>
        </div>
      )}

      {entries.length === 0 ? (
        <EmptyState title="No downloads" description="The download queue is empty." />
      ) : (
        <div className="space-y-2">
          <div className="flex items-center px-4 py-2">
            <input
              type="checkbox"
              checked={selected.length === entries.length && entries.length > 0}
              onChange={selectAll}
              className="mr-3"
            />
            <span className="text-xs text-gray-500">Select all</span>
          </div>
          {entries.map((entry) => (
            <div
              key={entry.id}
              className={`bg-white rounded-lg border p-4 ${
                entry.read ? 'border-gray-100 opacity-60' : 'border-gray-200'
              }`}
            >
              <div className="flex items-start gap-3">
                <input
                  type="checkbox"
                  checked={selected.includes(entry.id)}
                  onChange={() => toggleSelect(entry.id)}
                  className="mt-1"
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-medium text-gray-900 truncate">
                      {entry.book_title || entry.asin}
                    </span>
                    <Badge color={entry.stalled ? 'yellow' : statusColors[entry.status] || 'gray'}>
                      {entry.stalled ? `${entry.status} (stuck)` : entry.status}
                    </Badge>
                    {entry.attempts > 1 && (
                      <span className="text-xs text-gray-500">
                        Attempt {entry.attempts}
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-gray-500 flex flex-wrap gap-x-3 gap-y-0.5 mt-0.5">
                    {entry.book_author && <span>{entry.book_author}</span>}
                    <span className="font-mono text-gray-400">{entry.asin}</span>
                    {entry.account_username && <span>{entry.account_username}</span>}
                    {entry.file_size_bytes && <span>{formatFileSize(entry.file_size_bytes)}</span>}
                    {entry.download_speed_kbps && <span>{(entry.download_speed_kbps / 1024).toFixed(1)} MB/s</span>}
                    {entry.download_quality && <span>{entry.download_quality}</span>}
                    {entry.duration_seconds && <span>{formatDuration(entry.duration_seconds)}</span>}
                    {entry.attempts > 1 && <span>{entry.attempts} attempts</span>}
                    <span>{timeAgo(entry.created_at)}</span>
                  </div>
                  {entry.error_message && (
                    <p className="text-xs text-red-600 mt-1">{entry.error_message}</p>
                  )}
                </div>
                <div className="flex items-center gap-1 flex-shrink-0">
                  {(entry.status === 'failed' || entry.stalled) && (
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => retry.mutate(entry.id)}
                      disabled={retry.isPending}
                    >
                      Retry
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      patch.mutate({ id: entry.id, data: { read: !entry.read } })
                    }
                  >
                    {entry.read ? 'Unread' : 'Read'}
                  </Button>
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={() => {
                      if (confirm('Remove this download entry?')) {
                        remove.mutate(entry.id);
                      }
                    }}
                  >
                    Remove
                  </Button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
