import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../client';
import type { AuditResult } from '../types';

export function useAuditStatus() {
  return useQuery<{ last_run_id: number | null; running_run_id: number | null }>({
    queryKey: ['audit-status'],
    queryFn: () => apiFetch('/audit'),
  });
}

export function useAuditResults(auditId: number | undefined) {
  return useQuery<{
    results: AuditResult[];
    summary: {
      total_scanned: number;
      mismatches: number;
      missing_files: number;
      good: number;
      status: string;
    };
  }>({
    queryKey: ['audit-results', auditId],
    queryFn: () => apiFetch(`/audit/results/${auditId}`),
    enabled: !!auditId,
  });
}

export function useAuditActions() {
  const qc = useQueryClient();

  const startAudit = useMutation({
    mutationFn: () =>
      apiFetch<{ audit_id: number; already_running: boolean }>('/audit/start', {
        method: 'POST',
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['audit-status'] }),
  });

  const unmatchFile = useMutation({
    mutationFn: (filePath: string) =>
      apiFetch('/audit/unmatch', {
        method: 'POST',
        body: JSON.stringify({ file_path: filePath }),
      }),
  });

  return { startAudit, unmatchFile };
}
