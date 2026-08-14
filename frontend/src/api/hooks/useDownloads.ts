import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query';
import { apiFetch } from '../client';
import type { DownloadsResponse } from '../types';

/** Poll cadence while downloads are in flight or waiting to start. */
const DOWNLOADS_ACTIVE_POLL_MS = 3000;
/** Poll cadence when the queue is idle — enough to notice a scheduler pickup. */
const DOWNLOADS_IDLE_POLL_MS = 20000;

interface DownloadFilters {
  search?: string;
  status?: string;
  read_status?: string;
  account?: string;
  book_id?: number;
  date_from?: string;
  date_to?: string;
  sort?: string;
  order?: string;
}

export function useDownloads(filters: DownloadFilters = {}) {
  const params = new URLSearchParams();
  if (filters.search) params.set('search', filters.search);
  if (filters.status) params.set('status', filters.status);
  if (filters.read_status) params.set('read_status', filters.read_status);
  if (filters.account) params.set('account', filters.account);
  if (filters.book_id) params.set('book_id', String(filters.book_id));
  if (filters.date_from) params.set('date_from', filters.date_from);
  if (filters.date_to) params.set('date_to', filters.date_to);
  if (filters.sort) params.set('sort', filters.sort);
  if (filters.order) params.set('order', filters.order);

  const qs = params.toString();
  return useQuery<DownloadsResponse>({
    // Keep the previous page's data on screen while a new filter loads.
    // Without it the page unmounts on every keystroke and the search input
    // loses focus — same fix as the library page. It also keeps the live
    // refresh below from flickering the page on every tick.
    placeholderData: keepPreviousData,
    queryKey: ['downloads', qs],
    queryFn: () => apiFetch(`/downloads?${qs}`),

    // Live refresh, paced by whether anything is actually moving. A queue with
    // active downloads changes second to second; an idle one does not, and
    // polling it hard just burns queries. Same shape as useJob's interval.
    refetchInterval: (query) => {
      const stats = query.state.data?.stats;
      if (!stats) return DOWNLOADS_IDLE_POLL_MS;
      const active = stats.in_flight > 0 || stats.pending > 0;
      return active ? DOWNLOADS_ACTIVE_POLL_MS : DOWNLOADS_IDLE_POLL_MS;
    },
    // Background tabs stop polling (this is the default; stated because the
    // whole point here is to not have the page hammering the API unattended).
    refetchIntervalInBackground: false,
    // A queue that changed while the tab was hidden should be current the
    // moment it's looked at again, rather than after the next tick.
    refetchOnWindowFocus: true,
  });
}

export function useDownloadActions() {
  const qc = useQueryClient();

  const retry = useMutation({
    mutationFn: (id: number) =>
      apiFetch(`/downloads/${id}/retry`, { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['downloads'] }),
  });

  const remove = useMutation({
    mutationFn: (id: number) =>
      apiFetch(`/downloads/${id}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['downloads'] }),
  });

  const patch = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Record<string, unknown> }) =>
      apiFetch(`/downloads/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['downloads'] }),
  });

  const bulk = useMutation({
    mutationFn: (body: { action: string; entry_ids: number[] }) =>
      apiFetch('/downloads/bulk', {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['downloads'] }),
  });

  const reapStale = useMutation({
    mutationFn: () =>
      apiFetch<{ checked: number; requeued: number; failed: number }>(
        '/downloads/reap-stale',
        { method: 'POST' }
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['downloads'] }),
  });

  const processQueue = useMutation({
    mutationFn: () =>
      apiFetch<{ job_id: number }>('/downloads/process', { method: 'POST' }),
  });

  return { retry, remove, patch, bulk, reapStale, processQueue };
}
