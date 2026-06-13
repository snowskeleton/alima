import { useState } from 'react';
import { useAuditStatus, useAuditResults, useAuditActions } from '../api/hooks/useAudit';
import { useSSE } from '../utils/sse';
import { PageSpinner } from '../components/ui/Spinner';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Alert } from '../components/ui/Alert';
import { EmptyState } from '../components/ui/EmptyState';

interface AuditProgress {
  scanned: number;
  total: number;
  current_book?: string;
}

const statusColors: Record<string, 'green' | 'yellow' | 'red' | 'gray'> = {
  good: 'green',
  warning: 'yellow',
  bad: 'red',
  missing: 'gray',
};

export function AuditPage() {
  const { data: status, isLoading } = useAuditStatus();
  const { startAudit, unmatchFile } = useAuditActions();
  const [activeAuditId, setActiveAuditId] = useState<number | null>(null);
  const [filter, setFilter] = useState<string>('all');

  const auditId = activeAuditId ?? status?.running_run_id ?? status?.last_run_id;
  const isRunning = !!(activeAuditId ?? status?.running_run_id);

  const { data: progress } = useSSE<AuditProgress>({
    url: `/api/v2/audit/stream/${auditId}`,
    event: 'audit_progress',
    enabled: isRunning && !!auditId,
  });

  const { data: results } = useAuditResults(
    !isRunning ? (auditId ?? undefined) : undefined
  );

  if (isLoading) return <PageSpinner />;

  const handleStart = async () => {
    const result = await startAudit.mutateAsync();
    if (!result.already_running) {
      setActiveAuditId(result.audit_id);
    }
  };

  const allResults = results?.results ?? [];
  const summary = results?.summary;

  const filteredResults =
    filter === 'all'
      ? allResults
      : allResults.filter((r) => r.status === filter);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Library Audit</h1>
        <Button
          onClick={handleStart}
          disabled={startAudit.isPending || isRunning}
        >
          {isRunning ? 'Running...' : 'Start Audit'}
        </Button>
      </div>

      {isRunning && progress && (
        <Alert type="info" className="mb-4">
          <p>
            Scanning: {progress.scanned}/{progress.total}
            {progress.current_book && (
              <span className="ml-2 text-gray-500">— {progress.current_book}</span>
            )}
          </p>
          <div className="mt-2 bg-blue-200 rounded-full h-2">
            <div
              className="bg-blue-600 rounded-full h-2 transition-all"
              style={{
                width: progress.total
                  ? `${(progress.scanned / progress.total) * 100}%`
                  : '0%',
              }}
            />
          </div>
        </Alert>
      )}

      {summary && (
        <div className="grid grid-cols-4 gap-3 mb-6">
          <div className="bg-white p-3 rounded-lg border border-gray-200 text-center">
            <div className="text-2xl font-bold text-gray-900">{summary.total_scanned}</div>
            <div className="text-xs text-gray-500">Scanned</div>
          </div>
          <div className="bg-white p-3 rounded-lg border border-gray-200 text-center">
            <div className="text-2xl font-bold text-green-600">{summary.good}</div>
            <div className="text-xs text-gray-500">Good</div>
          </div>
          <div className="bg-white p-3 rounded-lg border border-gray-200 text-center">
            <div className="text-2xl font-bold text-yellow-600">{summary.mismatches}</div>
            <div className="text-xs text-gray-500">Mismatches</div>
          </div>
          <div className="bg-white p-3 rounded-lg border border-gray-200 text-center">
            <div className="text-2xl font-bold text-gray-500">{summary.missing_files}</div>
            <div className="text-xs text-gray-500">Missing Files</div>
          </div>
        </div>
      )}

      {allResults.length > 0 && (
        <>
          <div className="flex gap-2 mb-4">
            {['all', 'good', 'warning', 'bad', 'missing'].map((f) => (
              <Button
                key={f}
                variant={filter === f ? 'primary' : 'ghost'}
                size="sm"
                onClick={() => setFilter(f)}
              >
                {f.charAt(0).toUpperCase() + f.slice(1)}
                {f !== 'all' && (
                  <span className="ml-1 text-xs">
                    ({allResults.filter((r) => r.status === f).length})
                  </span>
                )}
              </Button>
            ))}
          </div>

          <div className="space-y-2">
            {filteredResults.map((result, idx) => (
              <div
                key={idx}
                className="bg-white rounded-lg border border-gray-200 p-4"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <Badge color={statusColors[result.status]}>
                        {result.status}
                      </Badge>
                      <span className="font-medium text-gray-900 truncate">
                        {result.book_title}
                      </span>
                    </div>
                    <div className="text-xs text-gray-500">
                      <span>by {result.book_author}</span>
                    </div>
                    {result.status !== 'missing' && result.file_title && (
                      <div className="text-xs text-gray-400 mt-1">
                        File: {result.file_title} by {result.file_author}
                        <span className="ml-2">
                          (title: {Math.round(result.title_score * 100)}%, author:{' '}
                          {Math.round(result.author_score * 100)}%)
                        </span>
                      </div>
                    )}
                    <div className="text-xs text-gray-400 mt-1 font-mono truncate">
                      {result.file_path}
                    </div>
                  </div>
                  {(result.status === 'bad' || result.status === 'warning') && (
                    <Button
                      variant="danger"
                      size="sm"
                      onClick={() => {
                        if (confirm('Unmatch this file from its book?')) {
                          unmatchFile.mutate(result.file_path);
                        }
                      }}
                      disabled={unmatchFile.isPending}
                    >
                      Unmatch
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {!isRunning && allResults.length === 0 && !summary && (
        <EmptyState
          title="No audit results"
          description="Run an audit to check your library files against book metadata."
          action={
            <Button onClick={handleStart} disabled={startAudit.isPending}>
              Start Audit
            </Button>
          }
        />
      )}
    </div>
  );
}
