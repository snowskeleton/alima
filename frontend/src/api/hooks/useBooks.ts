import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../client';
import type { Book, BooksResponse } from '../types';

interface BookFilters {
  search?: string;
  status?: string;
  source?: string;
  series_filter?: string;
  sort?: string;
  order?: string;
  limit?: number;
  offset?: number;
}

export function useBooks(filters: BookFilters = {}) {
  const params = new URLSearchParams();
  if (filters.search) params.set('search', filters.search);
  if (filters.status) params.set('status', filters.status);
  if (filters.source) params.set('source', filters.source);
  if (filters.series_filter) params.set('series_filter', filters.series_filter);
  if (filters.sort) params.set('sort', filters.sort);
  if (filters.order) params.set('order', filters.order);
  if (filters.limit) params.set('limit', String(filters.limit));
  if (filters.offset) params.set('offset', String(filters.offset));

  const qs = params.toString();
  return useQuery<BooksResponse>({
    queryKey: ['books', qs],
    queryFn: () => apiFetch(`/books?${qs}`),
  });
}

export function useBook(bookId: number | undefined) {
  return useQuery<Book>({
    queryKey: ['book', bookId],
    queryFn: () => apiFetch(`/books/${bookId}`),
    enabled: !!bookId,
  });
}

export function useBookActions() {
  const qc = useQueryClient();

  const downloadBook = useMutation({
    mutationFn: (bookId: number) =>
      apiFetch(`/books/${bookId}/download`, { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['books'] }),
  });

  const toggleDownload = useMutation({
    mutationFn: ({ bookId, enabled }: { bookId: number; enabled: boolean }) =>
      apiFetch(`/books/${bookId}`, {
        method: 'PATCH',
        body: JSON.stringify({ download_enabled: enabled }),
      }),
    onSuccess: (_, { bookId }) => {
      qc.invalidateQueries({ queryKey: ['book', bookId] });
      qc.invalidateQueries({ queryKey: ['books'] });
    },
  });

  const markAvailable = useMutation({
    mutationFn: (bookId: number) =>
      apiFetch(`/books/${bookId}`, {
        method: 'PATCH',
        body: JSON.stringify({ mark_available: true }),
      }),
    onSuccess: (_, bookId) => {
      qc.invalidateQueries({ queryKey: ['book', bookId] });
    },
  });

  const unmatchBook = useMutation({
    mutationFn: (bookId: number) =>
      apiFetch(`/books/${bookId}/unmatch`, { method: 'POST' }),
    onSuccess: (_, bookId) => {
      qc.invalidateQueries({ queryKey: ['book', bookId] });
    },
  });

  const deleteFile = useMutation({
    mutationFn: (bookId: number) =>
      apiFetch(`/books/${bookId}/file`, { method: 'DELETE' }),
    onSuccess: (_, bookId) => {
      qc.invalidateQueries({ queryKey: ['book', bookId] });
    },
  });

  const deleteBook = useMutation({
    mutationFn: (bookId: number) =>
      apiFetch(`/books/${bookId}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['books'] }),
  });

  const updateMetadata = useMutation({
    mutationFn: ({ bookId, data }: { bookId: number; data: Record<string, string> }) =>
      apiFetch(`/books/${bookId}/metadata`, {
        method: 'PUT',
        body: JSON.stringify(data),
      }),
    onSuccess: (_, { bookId }) => {
      qc.invalidateQueries({ queryKey: ['book', bookId] });
    },
  });

  const resetMetadata = useMutation({
    mutationFn: (bookId: number) =>
      apiFetch(`/books/${bookId}/metadata`, { method: 'DELETE' }),
    onSuccess: (_, bookId) => {
      qc.invalidateQueries({ queryKey: ['book', bookId] });
    },
  });

  return {
    downloadBook,
    toggleDownload,
    markAvailable,
    unmatchBook,
    deleteFile,
    deleteBook,
    updateMetadata,
    resetMetadata,
  };
}

export function useBulkBookActions() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: ({ action, bookIds }: { action: string; bookIds: number[] }) =>
      apiFetch<{ success: boolean; affected: number }>('/books/bulk', {
        method: 'POST',
        body: JSON.stringify({ action, book_ids: bookIds }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['books'] }),
  });
}
