import { useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { useAuth } from '../api/hooks/useAuth';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Alert } from '../components/ui/Alert';

export function RegisterPage() {
  const { authenticated, needsRegistration, register: registerMut } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');

  if (!needsRegistration && !authenticated) return <Navigate to="/auth/login" replace />;
  if (authenticated) return <Navigate to="/library" replace />;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    registerMut.mutate(email, {
      onSuccess: () => navigate('/library'),
    });
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="max-w-sm w-full">
        <h1 className="text-2xl font-bold text-center text-gray-900 mb-2">Welcome to Alima</h1>
        <p className="text-center text-gray-500 mb-8">Create your admin account to get started.</p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            label="Email address"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoFocus
          />

          {registerMut.isError && (
            <Alert type="error">Registration failed. Please try again.</Alert>
          )}

          <Button type="submit" className="w-full" disabled={registerMut.isPending}>
            {registerMut.isPending ? 'Creating...' : 'Create Admin Account'}
          </Button>
        </form>
      </div>
    </div>
  );
}
