import { useEffect, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { apiFetch } from '../api/client';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Select } from '../components/ui/Select';
import { Alert } from '../components/ui/Alert';

// A pending login is kept here so the page can be closed while waiting for the
// account's owner to sign in and send the redirect URL back.
const PENDING_KEY = 'alima.pendingAudibleLogin';

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

  useEffect(() => {
    const saved = localStorage.getItem(PENDING_KEY);
    if (!saved) return;
    try {
      const pending = JSON.parse(saved);
      if (!pending.sessionId || !pending.oauthUrl) return;
      setSessionId(pending.sessionId);
      setOauthUrl(pending.oauthUrl);
      setMarketplace(pending.marketplace ?? 'us');
      setStep('waiting');
    } catch {
      localStorage.removeItem(PENDING_KEY);
    }
  }, []);

  const discardPending = () => {
    localStorage.removeItem(PENDING_KEY);
    setSessionId('');
    setOauthUrl('');
    setRedirectUrl('');
    setError('');
    setStep('start');
  };

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
      localStorage.setItem(
        PENDING_KEY,
        JSON.stringify({ sessionId: data.session_id, oauthUrl: data.oauth_url, marketplace }),
      );
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
      localStorage.removeItem(PENDING_KEY);
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
              1. Open this URL and sign in to Amazon, or send it to the account's owner:
            </p>
            <div className="bg-gray-50 p-3 rounded text-xs font-mono break-all">
              <a href={oauthUrl} target="_blank" rel="noopener noreferrer" className="text-indigo-600">
                {oauthUrl.slice(0, 80)}...
              </a>
            </div>
            <button
              type="button"
              onClick={() => navigator.clipboard.writeText(oauthUrl)}
              className="mt-2 text-xs text-indigo-600 hover:text-indigo-800"
            >
              Copy login URL
            </button>
            <p className="mt-2 text-xs text-gray-400">
              You can close this page — come back here to paste the redirect URL when you get it.
              This login stays valid for 7 days.
            </p>
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
          <div className="flex items-center gap-4">
            <Button onClick={completeLogin} disabled={loading || !redirectUrl}>
              {loading ? 'Completing...' : 'Complete Login'}
            </Button>
            <button
              type="button"
              onClick={discardPending}
              className="text-sm text-gray-500 hover:text-gray-700"
            >
              Start over
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
