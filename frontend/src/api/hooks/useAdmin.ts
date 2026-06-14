import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../client';
import type { ApiKey, User } from '../types';

export function useUsers(sort = 'created_desc') {
  return useQuery<{ users: User[] }>({
    queryKey: ['users', sort],
    queryFn: () => apiFetch(`/users?sort=${sort}`),
  });
}

export function useUserActions() {
  const qc = useQueryClient();

  const createUser = useMutation({
    mutationFn: (body: { email: string; role?: string }) =>
      apiFetch('/users', { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
  });

  const patchUser = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Record<string, unknown> }) =>
      apiFetch(`/users/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
  });

  const deleteUser = useMutation({
    mutationFn: (id: number) =>
      apiFetch(`/users/${id}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
  });

  const sendLoginLink = useMutation({
    mutationFn: (id: number) =>
      apiFetch(`/users/${id}/send-login-link`, { method: 'POST' }),
  });

  return { createUser, patchUser, deleteUser, sendLoginLink };
}

export function useApiKeys() {
  return useQuery<{ api_keys: ApiKey[] }>({
    queryKey: ['api-keys'],
    queryFn: () => apiFetch('/api-keys'),
  });
}

export function useApiKeyActions() {
  const qc = useQueryClient();

  const createKey = useMutation({
    mutationFn: (name: string) =>
      apiFetch<{ key: string; key_id: number; name: string; prefix: string }>(
        '/api-keys',
        { method: 'POST', body: JSON.stringify({ name }) },
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['api-keys'] }),
  });

  const deleteKey = useMutation({
    mutationFn: (id: number) =>
      apiFetch(`/api-keys/${id}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['api-keys'] }),
  });

  return { createKey, deleteKey };
}

export function useSettings() {
  return useQuery<{ settings: Record<string, string | null> }>({
    queryKey: ['settings'],
    queryFn: () => apiFetch('/settings'),
  });
}

export function useSettingsActions() {
  const qc = useQueryClient();

  const updateSettings = useMutation({
    mutationFn: (data: Record<string, string | null>) =>
      apiFetch('/settings', { method: 'PUT', body: JSON.stringify(data) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['settings'] }),
  });

  const testEmail = useMutation({
    mutationFn: (recipient: string) =>
      apiFetch('/settings/test-email', {
        method: 'POST',
        body: JSON.stringify({ recipient_email: recipient }),
      }),
  });

  const removeDefaultCover = useMutation({
    mutationFn: () => apiFetch('/settings/default-cover', { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['settings'] }),
  });

  return { updateSettings, testEmail, removeDefaultCover };
}

export interface LogEntry {
  timestamp: string | null;
  module: string | null;
  level: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL' | 'OTHER';
  message: string;
}

export interface LogFailure {
  asin: string;
  book_title: string | null;
  created_at: string;
  error_message: string | null;
}

export interface LogStats {
  total_downloads: number;
  successful_downloads: number;
  failed_downloads: number;
  pending_downloads: number;
  total_bytes: number;
  average_speed_kbps: number;
  average_duration_seconds: number;
  downloads_by_day: { date: string; count: number }[];
  top_quality: string | null;
  recent_failures: LogFailure[];
}

export interface LogDownload {
  id: number;
  asin: string;
  book_title: string | null;
  status: string;
  file_size_bytes: number | null;
  duration_seconds: number | null;
  download_speed_kbps: number | null;
  download_quality: string | null;
  attempts: number;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
}

export function useLogs(view: 'stats' | 'downloads' | 'raw', days = 7, lines = 500) {
  return useQuery<{ entries?: LogEntry[]; downloads?: LogDownload[] } & Partial<LogStats>>({
    queryKey: ['logs', view, days, lines],
    queryFn: () => apiFetch(`/logs?view=${view}&days=${days}&lines=${lines}`),
  });
}

export function useForceRefreshMetadata() {
  return useMutation({
    mutationFn: () =>
      apiFetch<{ job_id: number }>('/sync/force-refresh-metadata', { method: 'POST' }),
  });
}
