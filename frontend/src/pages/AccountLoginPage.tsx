import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { apiFetch } from '../api/client';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Select } from '../components/ui/Select';
import { Alert } from '../components/ui/Alert';

export function AccountLoginPage() {
  const navigate = useNavigate();
  const [marketplace, setMarketplace] = useState('us');
  const [withUsername, setWithUsername] = useState(false);
  const [step, setStep] = useState<'start' | 'waiting' | 'complete'>('start');
  const [oauthUrl, setOauthUrl] = useState('');
  const [sessionId, setSessionId] = useState('');
  const [redirectUrl, setRedirectUrl] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const marketplaces = [
    { value: 'us', label: 'United States' },
    { value: 'uk', label: 'United Kingdom' },
    { value: 'de', label: 'Germany' },
    { value: 'fr', label: 'France' },
    { value: 'ca', label: 'Canada' },
    { value: 'au', label: 'Australia' },
    { value: 'in', label: 'India' },
    { value: 'it', label: 'Italy' },
    { value: 'jp', label: 'Japan' },
    { value: 'es', label: 'Spain' },
  ];

  const generateUrl = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await apiFetch<{ session_id: string; oauth_url: string }>(
        '/accounts/login/generate-url',
        { method: 'POST', body: JSON.stringify({ marketplace, with_username: withUsername }) },
      );
      setSessionId(data.session_id);
      setOauthUrl(data.oauth_url);
      setStep('waiting');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to generate URL');
    } finally {
      setLoading(false);
    }
  };

  const completeLogin = async () => {
    setLoading(true);
    setError('');
    try {
      await apiFetch('/accounts/login/complete', {
        method: 'POST',
        body: JSON.stringify({ session_id: sessionId, redirect_url: redirectUrl }),
      });
      navigate('/admin/accounts');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-lg">
      <div className="mb-4">
        <Link to="/admin/accounts" className="text-sm text-indigo-600 hover:text-indigo-800">&larr; Back to Accounts</Link>
      </div>

      <h1 className="text-2xl font-bold text-gray-900 mb-6">Add Audible Account</h1>

      {error && <Alert type="error" className="mb-4">{error}</Alert>}

      {step === 'start' && (
        <div className="bg-white p-6 rounded-lg border border-gray-200 space-y-4">
          <Select label="Marketplace" value={marketplace} onChange={(e) => setMarketplace(e.target.value)} options={marketplaces} />
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-0.5" checked={withUsername} onChange={e => setWithUsername(e.target.checked)} />
            <span>
              I have a pre-Amazon Audible account (username instead of email)
              <span className="block text-xs text-gray-400">Only check this if you registered with Audible before Amazon acquired it — very rare</span>
            </span>
          </label>
          <Button onClick={generateUrl} disabled={loading}>
            {loading ? 'Generating...' : 'Generate Login URL'}
          </Button>
        </div>
      )}

      {step === 'waiting' && (
        <div className="bg-white p-6 rounded-lg border border-gray-200 space-y-4">
          <div>
            <p className="text-sm text-gray-700 mb-2">
              1. Open this URL in your browser and sign in to Amazon:
            </p>
            <div className="bg-gray-50 p-3 rounded text-xs font-mono break-all">
              <a href={oauthUrl} target="_blank" rel="noopener noreferrer" className="text-indigo-600">
                {oauthUrl.slice(0, 80)}...
              </a>
            </div>
          </div>
          <div>
            <p className="text-sm text-gray-700 mb-2">
              2. After login, copy the redirect URL from your browser and paste it here:
            </p>
            <Input
              placeholder="Paste the redirect URL here..."
              value={redirectUrl}
              onChange={(e) => setRedirectUrl(e.target.value)}
            />
          </div>
          <Button onClick={completeLogin} disabled={loading || !redirectUrl}>
            {loading ? 'Completing...' : 'Complete Login'}
          </Button>
        </div>
      )}
    </div>
  );
}
