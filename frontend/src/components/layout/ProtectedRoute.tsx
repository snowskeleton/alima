import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '../../api/hooks/useAuth';
import { PageSpinner } from '../ui/Spinner';

export function ProtectedRoute() {
  const { authenticated, needsRegistration, isLoading } = useAuth();

  if (isLoading) return <PageSpinner />;

  if (needsRegistration) return <Navigate to="/auth/register" replace />;

  if (!authenticated) return <Navigate to="/auth/login" replace />;

  return <Outlet />;
}
