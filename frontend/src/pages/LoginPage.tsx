import { useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { useAuth } from '../api/hooks/useAuth';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Alert } from '../components/ui/Alert';

export function LoginPage() {
  const { authenticated, needsRegistration, login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');

  if (needsRegistration) return <Navigate to="/auth/register" replace />;
  if (authenticated) return <Navigate to="/library" replace />;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    login.mutate(email, {
      onSuccess: () => navigate('/auth/magic-link-sent', { state: { email } }),
    });
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="max-w-sm w-full">
        <h1 className="text-2xl font-bold text-center text-gray-900 mb-8">Sign in to Alima</h1>

        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            label="Email address"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoFocus
          />

          {login.isError && (
            <Alert type="error">Failed to send login link. Please try again.</Alert>
          )}

          <Button type="submit" className="w-full" disabled={login.isPending}>
            {login.isPending ? 'Sending...' : 'Send Magic Link'}
          </Button>
        </form>
      </div>
    </div>
  );
}
