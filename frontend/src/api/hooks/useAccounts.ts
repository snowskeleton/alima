import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../client';
import type { AudibleAccount } from '../types';

export function useAccounts({ enabled = true }: { enabled?: boolean } = {}) {
  return useQuery<{ accounts: AudibleAccount[] }>({
    queryKey: ['accounts'],
    queryFn: () => apiFetch('/accounts'),
    enabled,
  });
}

export interface DeregisterPreviousDevicesResult {
  removed: number;
  /** device: the last characters of the device serial. */
  failed: { device: string; error: string }[];
  previous_devices: number;
}

export function useAccountActions() {
  const qc = useQueryClient();

  const patchAccount = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Record<string, unknown> }) =>
      apiFetch(`/accounts/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['accounts'] }),
  });

  const deleteAccount = useMutation({
    mutationFn: (id: number) =>
      apiFetch(`/accounts/${id}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['accounts'] }),
  });

  const syncAccount = useMutation({
    mutationFn: (id: number) =>
      apiFetch<{ job_id: number }>(`/accounts/${id}/sync`, { method: 'POST' }),
  });

  const queueAll = useMutation({
    mutationFn: (id: number) =>
      apiFetch(`/accounts/${id}/queue-all`, { method: 'POST' }),
  });

  const deregisterPreviousDevices = useMutation({
    mutationFn: (id: number) =>
      apiFetch<DeregisterPreviousDevicesResult>(
        `/accounts/${id}/deregister-previous-devices`,
        { method: 'POST' },
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['accounts'] }),
  });

  return { patchAccount, deleteAccount, syncAccount, queueAll, deregisterPreviousDevices };
}
