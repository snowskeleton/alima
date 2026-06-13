import { useEffect, useState } from 'react';
import { useSearchParams, Navigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../api/client';
import { PageSpinner } from '../components/ui/Spinner';
import { Alert } from '../components/ui/Alert';

export function MagicLinkCallbackPage() {
  const [params] = useSearchParams();
  const token = params.get('token');
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading');
  const [error, setError] = useState('');

  useEffect(() => {
    if (!token) {
      setStatus('error');
      setError('No token provided');
      return;
    }

    apiFetch(`/auth/magic-link?token=${encodeURIComponent(token)}`)
      .then(() => {
        queryClient.invalidateQueries({ queryKey: ['auth'] });
        setStatus('success');
      })
      .catch((e) => {
        setStatus('error');
        setError(e.message || 'Invalid or expired magic link');
      });
  }, [token, queryClient]);

  if (status === 'loading') return <PageSpinner />;
  if (status === 'success') return <Navigate to="/library" replace />;

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="max-w-sm w-full text-center">
        <Alert type="error">{error}</Alert>
        <a href="/auth/login" className="mt-4 inline-block text-sm text-indigo-600 hover:text-indigo-800">
          Back to login
        </a>
      </div>
    </div>
  );
}
