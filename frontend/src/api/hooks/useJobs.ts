import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../client';
import type { BackgroundJob } from '../types';

export function useJob(jobId: number | undefined) {
  return useQuery<BackgroundJob>({
    queryKey: ['job', jobId],
    queryFn: () => apiFetch(`/jobs/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === 'completed' || status === 'failed') return false;
      return 1000;
    },
  });
}
