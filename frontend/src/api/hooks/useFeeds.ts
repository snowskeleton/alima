import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../client';
import type { Feed } from '../types';

export function useFeeds() {
  return useQuery<{ feeds: Feed[] }>({
    queryKey: ['feeds'],
    queryFn: () => apiFetch('/feeds'),
  });
}

export function useFeed(feedId: number | undefined) {
  return useQuery<Feed>({
    queryKey: ['feed', feedId],
    queryFn: () => apiFetch(`/feeds/${feedId}`),
    enabled: !!feedId,
  });
}

export function useFeedBySlug(slug: string | undefined) {
  return useQuery<Feed>({
    queryKey: ['feed-slug', slug],
    queryFn: () => apiFetch(`/feeds/by-slug/${slug}`),
    enabled: !!slug,
  });
}

export function useFeedActions() {
  const qc = useQueryClient();

  const deleteFeed = useMutation({
    mutationFn: (feedId: number) =>
      apiFetch(`/feeds/${feedId}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['feeds'] }),
  });

  const patchFeed = useMutation({
    mutationFn: ({ feedId, data }: { feedId: number; data: Record<string, unknown> }) =>
      apiFetch(`/feeds/${feedId}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['feeds'] }),
  });

  const addBook = useMutation({
    mutationFn: ({ feedId, bookId }: { feedId: number; bookId: number }) =>
      apiFetch(`/feeds/${feedId}/books`, {
        method: 'POST',
        body: JSON.stringify({ book_id: bookId }),
      }),
    onSuccess: (_, { feedId }) => qc.invalidateQueries({ queryKey: ['feed', feedId] }),
  });

  const removeBook = useMutation({
    mutationFn: ({ feedId, bookId }: { feedId: number; bookId: number }) =>
      apiFetch(`/feeds/${feedId}/books/${bookId}`, { method: 'DELETE' }),
    onSuccess: (_, { feedId }) => qc.invalidateQueries({ queryKey: ['feed', feedId] }),
  });

  const removeCover = useMutation({
    mutationFn: (feedId: number) =>
      apiFetch(`/feeds/${feedId}/cover`, { method: 'DELETE' }),
    onSuccess: (_, feedId) => qc.invalidateQueries({ queryKey: ['feed', feedId] }),
  });

  return { deleteFeed, patchFeed, addBook, removeBook, removeCover };
}
