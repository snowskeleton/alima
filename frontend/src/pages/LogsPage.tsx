import { useState } from 'react';
import { useLogs, type LogEntry, type LogDownload, type LogStats } from '../api/hooks/useAdmin';
import { PageSpinner } from '../components/ui/Spinner';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { formatFileSize, formatDateTime } from '../utils/format';

type Tab = 'stats' | 'downloads' | 'raw';
type LogLevel = 'all' | 'INFO' | 'WARNING' | 'ERROR';

const LEVEL_ORDER: Record<string, number> = { DEBUG: 0, INFO: 1, WARNING: 2, ERROR: 3, CRITICAL: 4 };

const DAY_OPTIONS = [
  { value: 1, label: '24h' },
  { value: 7, label: '7d' },
  { value: 30, label: '30d' },
  { value: 90, label: '90d' },
];

// ── Stat card ──────────────────────────────────────────────────────────────

function StatCard({ label, value, sub, accent }: {
  label: string;
  value: string | number;
  sub?: string;
  accent?: 'green' | 'red' | 'yellow';
}) {
  const bg = accent === 'green' ? 'bg-green-50 border-green-200'
    : accent === 'red' ? 'bg-red-50 border-red-200'
    : accent === 'yellow' ? 'bg-yellow-50 border-yellow-200'
    : 'bg-white border-gray-200';

  return (
    <div className={`rounded-lg border p-4 ${bg}`}>
      <p className="text-sm text-gray-500 mb-1">{label}</p>
      <p className="text-2xl font-bold text-gray-900">{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
    </div>
  );
}

// ── Stats tab ──────────────────────────────────────────────────────────────

function StatsView({ data }: { data: LogStats }) {
  const maxDay = Math.max(...(data.downloads_by_day.map(d => d.count)), 1);
  const speedMbs = (data.average_speed_kbps / 1024).toFixed(1);
  const durMin = Math.floor(data.average_duration_seconds / 60);
  const durSec = Math.round(data.average_duration_seconds % 60);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard label="Total downloads" value={data.total_downloads} />
        <StatCard
          label="Successful"
          value={data.successful_downloads}
          sub={data.total_downloads ? `${((data.successful_downloads / data.total_downloads) * 100).toFixed(0)}%` : undefined}
          accent="green"
        />
        <StatCard
          label="Failed"
          value={data.failed_downloads}
          sub={data.total_downloads ? `${((data.failed_downloads / data.total_downloads) * 100).toFixed(0)}%` : undefined}
          accent={data.failed_downloads > 0 ? 'red' : undefined}
        />
        <StatCard label="Pending" value={data.pending_downloads} accent={data.pending_downloads > 0 ? 'yellow' : undefined} />
        <StatCard label="Total downloaded" value={formatFileSize(data.total_bytes) || '—'} />
        <StatCard label="Avg speed" value={data.average_speed_kbps ? `${speedMbs} MB/s` : '—'} />
        <StatCard label="Avg duration" value={data.average_duration_seconds ? `${durMin}m ${durSec}s` : '—'} />
        <StatCard label="Top quality" value={data.top_quality ?? '—'} />
      </div>

      {data.downloads_by_day.length > 0 && (
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">Downloads per day</h3>
          <div className="space-y-2">
            {data.downloads_by_day.map(d => (
              <div key={d.date} className="flex items-center gap-3">
                <span className="text-xs text-gray-500 w-24 shrink-0">{d.date}</span>
                <div className="flex-1 bg-gray-100 rounded-full h-5 overflow-hidden">
                  <div
                    className="bg-indigo-500 h-full rounded-full flex items-center justify-end pr-2"
                    style={{ width: `${Math.max((d.count / maxDay) * 100, 4)}%` }}
                  >
                    <span className="text-xs text-white font-medium">{d.count}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {data.recent_failures.length > 0 && (
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">Recent failures</h3>
          <div className="space-y-2">
            {data.recent_failures.map((f, i) => (
              <div key={i} className="bg-red-50 border border-red-200 rounded-lg p-3">
                <div className="flex items-start justify-between gap-2">
                  <span className="font-medium text-sm text-gray-900">
                    {f.book_title ?? f.asin}
                  </span>
                  <span className="text-xs text-gray-400 shrink-0">{formatDateTime(f.created_at)}</span>
                </div>
                {f.error_message && (
                  <p className="text-xs text-red-700 mt-1 font-mono">{f.error_message}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Download history tab ───────────────────────────────────────────────────

const STATUS_COLOR: Record<string, 'green' | 'red' | 'yellow' | 'blue' | 'gray'> = {
  completed: 'green',
  failed: 'red',
  pending: 'yellow',
  downloading: 'blue',
  decrypting: 'blue',
};

function DownloadsView({ downloads }: { downloads: LogDownload[] }) {
  if (!downloads.length) {
    return <p className="text-gray-400 text-sm">No downloads in this time range.</p>;
  }

  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 bg-gray-50">
            <th className="text-left px-4 py-3 font-medium text-gray-600">Book</th>
            <th className="text-left px-4 py-3 font-medium text-gray-600">Status</th>
            <th className="text-right px-4 py-3 font-medium text-gray-600">Size</th>
            <th className="text-right px-4 py-3 font-medium text-gray-600">Duration</th>
            <th className="text-right px-4 py-3 font-medium text-gray-600">Speed</th>
            <th className="text-right px-4 py-3 font-medium text-gray-600">Quality</th>
            <th className="text-right px-4 py-3 font-medium text-gray-600">Date</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {downloads.map(d => {
            const durMin = d.duration_seconds ? Math.floor(d.duration_seconds / 60) : null;
            const durSec = d.duration_seconds ? d.duration_seconds % 60 : null;
            const speedMbs = d.download_speed_kbps ? (d.download_speed_kbps / 1024).toFixed(1) : null;

            return (
              <tr key={d.id} className="hover:bg-gray-50">
                <td className="px-4 py-3">
                  <span className="text-gray-900 font-medium">{d.book_title ?? '—'}</span>
                  <span className="block text-xs text-gray-400 font-mono">{d.asin}</span>
                  {d.error_message && (
                    <span className="block text-xs text-red-600 mt-0.5">{d.error_message}</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  <Badge color={STATUS_COLOR[d.status] ?? 'gray'}>{d.status}</Badge>
                  {d.attempts > 1 && (
                    <span className="ml-1 text-xs text-gray-400">{d.attempts} attempts</span>
                  )}
                </td>
                <td className="px-4 py-3 text-right text-gray-600">
                  {formatFileSize(d.file_size_bytes) || '—'}
                </td>
                <td className="px-4 py-3 text-right text-gray-600">
                  {durMin !== null ? `${durMin}m ${durSec}s` : '—'}
                </td>
                <td className="px-4 py-3 text-right text-gray-600">
                  {speedMbs ? `${speedMbs} MB/s` : '—'}
                </td>
                <td className="px-4 py-3 text-right text-gray-600">
                  {d.download_quality ?? '—'}
                </td>
                <td className="px-4 py-3 text-right text-gray-400 text-xs whitespace-nowrap">
                  {formatDateTime(d.created_at)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Raw logs tab ───────────────────────────────────────────────────────────

const LEVEL_BADGE: Record<string, string> = {
  ERROR:    'bg-red-500 text-white',
  CRITICAL: 'bg-red-700 text-white',
  WARNING:  'bg-amber-400 text-white',
  INFO:     'bg-blue-500 text-white',
  DEBUG:    'bg-gray-400 text-white',
  OTHER:    'bg-gray-300 text-gray-700',
};

const LEVEL_ROW: Record<string, string> = {
  ERROR:    'bg-red-50 border-l-red-500',
  CRITICAL: 'bg-red-100 border-l-red-700',
  WARNING:  'bg-amber-50 border-l-amber-400',
  INFO:     'bg-blue-50 border-l-blue-400',
  DEBUG:    'bg-gray-50 border-l-gray-300',
  OTHER:    'bg-white border-l-transparent',
};

const FILTER_OPTIONS: { label: string; value: LogLevel }[] = [
  { label: 'All', value: 'all' },
  { label: 'Info+', value: 'INFO' },
  { label: 'Warnings+', value: 'WARNING' },
  { label: 'Errors only', value: 'ERROR' },
];

function RawLogsView({ entries }: { entries: LogEntry[] }) {
  const [minLevel, setMinLevel] = useState<LogLevel>('INFO');

  const visible = entries.filter(e => {
    if (minLevel === 'all') return true;
    return (LEVEL_ORDER[e.level] ?? -1) >= (LEVEL_ORDER[minLevel] ?? 0);
  });

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <span className="text-sm text-gray-500">Show:</span>
        {FILTER_OPTIONS.map(opt => (
          <button
            key={opt.value}
            onClick={() => setMinLevel(opt.value)}
            className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
              minLevel === opt.value
                ? 'bg-indigo-600 border-indigo-600 text-white'
                : 'border-gray-300 text-gray-600 hover:border-indigo-400 hover:text-indigo-600'
            }`}
          >
            {opt.label}
          </button>
        ))}
        <span className="ml-auto text-xs text-gray-400">{visible.length} entries</span>
      </div>

      <div className="space-y-1.5">
        {visible.length === 0 && (
          <p className="text-gray-400 text-sm py-4 text-center">No entries at this level.</p>
        )}
        {visible.map((entry, i) => (
          <div
            key={i}
            className={`flex items-baseline gap-2.5 px-3 py-2 rounded-md border-l-4 text-sm ${LEVEL_ROW[entry.level] ?? LEVEL_ROW.OTHER}`}
          >
            {entry.level !== 'OTHER' && (
              <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${LEVEL_BADGE[entry.level]}`}>
                {entry.level}
              </span>
            )}
            <span className="flex-1 text-gray-800 break-words">{entry.message}</span>
            {(entry.module || entry.timestamp) && (
              <span className="shrink-0 flex flex-col items-end gap-0.5 ml-2">
                {entry.module && (
                  <span className="text-[11px] font-medium text-gray-500">{entry.module}</span>
                )}
                {entry.timestamp && (
                  <span className="text-[10px] text-gray-400 whitespace-nowrap">{entry.timestamp}</span>
                )}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────

export function LogsPage() {
  const [tab, setTab] = useState<Tab>('raw');
  const [days, setDays] = useState(7);
  const [lines, setLines] = useState(500);

  const { data, isLoading, refetch } = useLogs(tab, days, lines);

  const tabs: { value: Tab; label: string }[] = [
    { value: 'raw', label: 'App Logs' },
    { value: 'stats', label: 'Stats' },
    { value: 'downloads', label: 'Download History' },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Logs</h1>
        <Button variant="secondary" onClick={() => refetch()}>Refresh</Button>
      </div>

      {/* Tab bar + controls */}
      <div className="flex items-center justify-between border-b border-gray-200">
        <div className="flex gap-1">
          {tabs.map(t => (
            <button
              key={t.value}
              onClick={() => setTab(t.value)}
              className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                tab === t.value
                  ? 'border-indigo-600 text-indigo-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2 pb-1">
          {tab !== 'raw' && (
            <>
              <span className="text-xs text-gray-500">Range:</span>
              {DAY_OPTIONS.map(opt => (
                <button
                  key={opt.value}
                  onClick={() => setDays(opt.value)}
                  className={`px-2.5 py-1 rounded text-xs font-medium border transition-colors ${
                    days === opt.value
                      ? 'bg-indigo-600 border-indigo-600 text-white'
                      : 'border-gray-300 text-gray-600 hover:border-indigo-400'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </>
          )}
          {tab === 'raw' && (
            <>
              <span className="text-xs text-gray-500">Last</span>
              <select
                value={lines}
                onChange={e => setLines(Number(e.target.value))}
                className="text-xs border border-gray-300 rounded px-2 py-1 text-gray-700"
              >
                {[200, 500, 1000, 2000, 5000].map(n => (
                  <option key={n} value={n}>{n} lines</option>
                ))}
              </select>
            </>
          )}
        </div>
      </div>

      {isLoading ? (
        <PageSpinner />
      ) : (
        <>
          {tab === 'stats' && data && <StatsView data={data as unknown as LogStats} />}
          {tab === 'downloads' && <DownloadsView downloads={(data?.downloads ?? []) as LogDownload[]} />}
          {tab === 'raw' && <RawLogsView entries={(data?.entries ?? []) as LogEntry[]} />}
        </>
      )}
    </div>
  );
}
