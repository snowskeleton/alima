import { useAuth } from '../api/hooks/useAuth';
import { Badge } from '../components/ui/Badge';
import { formatDateTime } from '../utils/format';

export function ProfilePage() {
  const { user } = useAuth();
  if (!user) return null;

  return (
    <div className="max-w-lg">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Profile</h1>
      <div className="bg-white rounded-lg border border-gray-200 p-6 space-y-4">
        <div>
          <span className="text-sm text-gray-500">Email</span>
          <p className="text-gray-900">{user.email}</p>
        </div>
        <div>
          <span className="text-sm text-gray-500">Role</span>
          <p><Badge color={user.role === 'admin' ? 'indigo' : 'gray'}>{user.role}</Badge></p>
        </div>
        <div>
          <span className="text-sm text-gray-500">Account Created</span>
          <p className="text-gray-900">{formatDateTime(user.created_at)}</p>
        </div>
        <div>
          <span className="text-sm text-gray-500">Last Login</span>
          <p className="text-gray-900">{formatDateTime(user.last_login)}</p>
        </div>
      </div>
    </div>
  );
}
