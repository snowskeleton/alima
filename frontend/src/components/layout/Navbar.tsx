import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../../api/hooks/useAuth';

export function Navbar() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const isAdmin = user?.role === 'admin';

  const navLinks = [
    { to: '/library', label: 'Library' },
    { to: '/feeds', label: 'Feeds' },
  ];

  const adminLinks = [
    { to: '/admin/accounts', label: 'Accounts' },
    { to: '/admin/downloads', label: 'Downloads' },
    { to: '/admin/users', label: 'Users' },
    { to: '/admin/settings', label: 'Settings' },
    { to: '/admin/import', label: 'Import' },
    { to: '/admin/match-books', label: 'Match' },
    { to: '/admin/audit', label: 'Audit' },
    { to: '/logs', label: 'Logs' },
  ];

  const isActive = (path: string) => location.pathname.startsWith(path);

  return (
    <nav className="bg-white border-b border-gray-200">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-14">
          <div className="flex items-center space-x-6">
            <Link to="/library" className="text-lg font-semibold text-indigo-600">
              Alima
            </Link>
            {navLinks.map((link) => (
              <Link
                key={link.to}
                to={link.to}
                className={`text-sm font-medium ${
                  isActive(link.to)
                    ? 'text-indigo-600 border-b-2 border-indigo-600'
                    : 'text-gray-500 hover:text-gray-700'
                } pb-px`}
              >
                {link.label}
              </Link>
            ))}
            {isAdmin &&
              adminLinks.map((link) => (
                <Link
                  key={link.to}
                  to={link.to}
                  className={`text-sm font-medium ${
                    isActive(link.to)
                      ? 'text-indigo-600 border-b-2 border-indigo-600'
                      : 'text-gray-500 hover:text-gray-700'
                  } pb-px`}
                >
                  {link.label}
                </Link>
              ))}
          </div>
          <div className="flex items-center space-x-4">
            {user && (
              <>
                <Link
                  to="/auth/profile"
                  className="text-sm text-gray-500 hover:text-gray-700"
                >
                  {user.email}
                </Link>
                <button
                  onClick={() => logout.mutate()}
                  className="text-sm text-gray-500 hover:text-gray-700"
                >
                  Logout
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </nav>
  );
}
