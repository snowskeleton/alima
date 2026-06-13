import { useLocation, Link } from 'react-router-dom';

export function MagicLinkSentPage() {
  const location = useLocation();
  const email = (location.state as { email?: string })?.email || 'your email';

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="max-w-sm w-full text-center">
        <h1 className="text-2xl font-bold text-gray-900 mb-4">Check your email</h1>
        <p className="text-gray-600 mb-6">
          We sent a magic link to <strong>{email}</strong>. Click the link in the email to sign in.
        </p>
        <Link to="/auth/login" className="text-sm text-indigo-600 hover:text-indigo-800">
          Back to login
        </Link>
      </div>
    </div>
  );
}
