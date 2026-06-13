import { useState } from 'react';
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

const statusColors: Record<string, 'gray' | 'green' | 'red' | 'yellow' | 'blue'> = {
  PENDING: 'gray',
  DOWNLOADING: 'blue',
  DECRYPTING: 'blue',
  COMPLETED: 'green',
  FAILED: 'red',
};

export function DownloadQueuePage() {
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [readStatus, setReadStatus] = useState('unread');
  const [sort, setSort] = useState('created_at');
  const [order, setOrder] = useState('desc');
  const [selected, setSelected] = useState<number[]>([]);
  const [processJobId, setProcessJobId] = useState<number>();

  const { data, isLoading } = useDownloads({ search, status, read_status: readStatus, sort, order });
  const { retry, remove, patch, bulk, processQueue } = useDownloadActions();
  const { data: job } = useJob(processJobId);

  if (isLoading) return <PageSpinner />;

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
        <h1 className="text-2xl font-bold text-gray-900">Download Queue</h1>
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
            <div className="text-2xl font-bold text-blue-600">{stats.downloading}</div>
            <div className="text-xs text-gray-500">Downloading</div>
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
          <Input
            placeholder="Search..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-48"
          />
          <Select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            options={[
              { value: '', label: 'All statuses' },
              { value: 'PENDING', label: 'Pending' },
              { value: 'DOWNLOADING', label: 'Downloading' },
              { value: 'COMPLETED', label: 'Completed' },
              { value: 'FAILED', label: 'Failed' },
            ]}
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
          <Select
            value={sort}
            onChange={(e) => setSort(e.target.value)}
            options={[
              { value: 'created_at', label: 'Created' },
              { value: 'priority', label: 'Priority' },
              { value: 'status', label: 'Status' },
            ]}
          />
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setOrder(order === 'desc' ? 'asc' : 'desc')}
          >
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
                    <Badge color={statusColors[entry.status] || 'gray'}>
                      {entry.status}
                    </Badge>
                    {entry.attempts > 1 && (
                      <span className="text-xs text-gray-500">
                        Attempt {entry.attempts}
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-gray-500 space-x-3">
                    {entry.book_author && <span>{entry.book_author}</span>}
                    {entry.account_username && <span>Account: {entry.account_username}</span>}
                    {entry.file_size_bytes && <span>{formatFileSize(entry.file_size_bytes)}</span>}
                    {entry.duration_seconds && <span>{formatDuration(entry.duration_seconds)}</span>}
                    <span>{timeAgo(entry.created_at)}</span>
                  </div>
                  {entry.error_message && (
                    <p className="text-xs text-red-600 mt-1">{entry.error_message}</p>
                  )}
                </div>
                <div className="flex items-center gap-1 flex-shrink-0">
                  {entry.status === 'FAILED' && (
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
