import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../client';
import type { AuthStatus } from '../types';

export function useAuth() {
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery<AuthStatus>({
    queryKey: ['auth'],
    queryFn: () => apiFetch('/auth/status'),
    staleTime: 60_000,
    retry: false,
  });

  const loginMutation = useMutation({
    mutationFn: (email: string) =>
      apiFetch<{ sent: boolean }>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email }),
      }),
  });

  const registerMutation = useMutation({
    mutationFn: (email: string) =>
      apiFetch('/auth/register', {
        method: 'POST',
        body: JSON.stringify({ email }),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['auth'] }),
  });

  const logoutMutation = useMutation({
    mutationFn: () => apiFetch('/auth/logout', { method: 'POST' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['auth'] }),
  });

  return {
    user: data?.user ?? null,
    authenticated: data?.authenticated ?? false,
    needsRegistration: data?.needs_registration ?? false,
    isLoading,
    login: loginMutation,
    register: registerMutation,
    logout: logoutMutation,
  };
}
