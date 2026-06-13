import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../client';
import type { DownloadsResponse } from '../types';

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
    queryKey: ['downloads', qs],
    queryFn: () => apiFetch(`/downloads?${qs}`),
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

  const processQueue = useMutation({
    mutationFn: () =>
      apiFetch<{ job_id: number }>('/downloads/process', { method: 'POST' }),
  });

  return { retry, remove, patch, bulk, processQueue };
}
