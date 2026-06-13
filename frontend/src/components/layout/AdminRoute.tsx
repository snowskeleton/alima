import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '../../api/hooks/useAuth';

export function AdminRoute() {
  const { user } = useAuth();

  if (user?.role !== 'admin') {
    return <Navigate to="/library" replace />;
  }

  return <Outlet />;
}
