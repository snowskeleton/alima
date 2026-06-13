import { useState } from 'react';
import { useLogs } from '../api/hooks/useAdmin';
import { PageSpinner } from '../components/ui/Spinner';
import { Button } from '../components/ui/Button';
import { Select } from '../components/ui/Select';
import { Input } from '../components/ui/Input';
import { formatFileSize } from '../utils/format';

export function LogsPage() {
  const [view, setView] = useState('stats');
  const [lines, setLines] = useState(200);
  const { data, isLoading, refetch } = useLogs(view, lines);

  if (isLoading) return <PageSpinner />;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Logs</h1>
        <div className="flex items-center gap-3">
          <Select
            value={view}
            onChange={(e) => setView(e.target.value)}
            options={[
              { value: 'stats', label: 'Stats' },
              { value: 'downloads', label: 'Download logs' },
              { value: 'raw', label: 'Raw logs' },
            ]}
          />
          {view !== 'stats' && (
            <Input
              type="number"
              value={String(lines)}
              onChange={(e) => setLines(Number(e.target.value) || 200)}
              className="w-24"
              placeholder="Lines"
            />
          )}
          <Button variant="secondary" onClick={() => refetch()}>
            Refresh
          </Button>
        </div>
      </div>

      {view === 'stats' && data?.stats && (
        <div className="space-y-3">
          {Object.entries(data.stats as Record<string, { size_bytes: number; modified: number }>).map(
            ([filename, info]) => (
              <div key={filename} className="bg-white rounded-lg border border-gray-200 p-4">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-gray-900 font-mono">{filename}</span>
                  <div className="text-sm text-gray-500">
                    {formatFileSize(info.size_bytes)}
                    <span className="ml-3">
                      Modified: {new Date(info.modified * 1000).toLocaleString()}
                    </span>
                  </div>
                </div>
              </div>
            )
          )}
        </div>
      )}

      {view !== 'stats' && data?.lines && (
        <div className="bg-gray-900 rounded-lg p-4 overflow-auto max-h-[70vh]">
          <pre className="text-xs text-gray-100 font-mono whitespace-pre-wrap">
            {(data.lines as string[]).join('\n')}
          </pre>
        </div>
      )}
    </div>
  );
}
