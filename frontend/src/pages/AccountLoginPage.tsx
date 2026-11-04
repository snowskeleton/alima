import { useEffect, useState } from 'react';
import { useNavigate, Link, useSearchParams } from 'react-router-dom';
import { apiFetch } from '../api/client';
import { useAccounts } from '../api/hooks/useAccounts';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Select } from '../components/ui/Select';
import { Alert } from '../components/ui/Alert';

// A pending login is kept here so the page can be closed while waiting for the
// account's owner to sign in and send the redirect URL back.
const PENDING_KEY = 'alima.pendingAudibleLogin';

interface CompleteResponse {
  success: boolean;
  username: string;
  reauthenticated?: boolean;
  previous_devices?: number;
}

/** The message the accounts list shows after a successful login. */
export interface AccountsNotice {
  type: 'success' | 'warning';
  message: string;
}

function noticeFor(result: CompleteResponse): AccountsNotice {
  if (!result.reauthenticated) {
    return { type: 'success', message: `Added ${result.username}.` };
  }
  return {
    type: 'success',
    message: result.previous_devices
      ? `Re-authenticated ${result.username}. Its old device is still registered with Amazon; ` +
        'use "Remove old device" once downloads work with the new one.'
      : `Re-authenticated ${result.username}.`,
  };
}

export function AccountLoginPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  // ?reauth=<account id> re-registers an existing account's device in place
  // instead of adding a new account.
  const reauthParam = searchParams.get('reauth');
  const reauthId = reauthParam && /^\d+$/.test(reauthParam) ? Number(reauthParam) : null;
  // Only needed to name the account being re-authenticated.
  const { data: accountsData } = useAccounts({ enabled: reauthId !== null });
  const reauthAccount = reauthId === null
    ? undefined
    : accountsData?.accounts.find(a => a.id === reauthId);
  // Each re-auth keeps its own pending login, so starting one doesn't clobber
  // a half-finished add (or a re-auth of a different account).
  const pendingKey = reauthId === null ? PENDING_KEY : `${PENDING_KEY}.reauth.${reauthId}`;
  const [marketplace, setMarketplace] = useState('us');
  const [withUsername, setWithUsername] = useState(false);
  const [step, setStep] = useState<'start' | 'waiting' | 'complete'>('start');
  const [oauthUrl, setOauthUrl] = useState('');
  const [sessionId, setSessionId] = useState('');
  const [redirectUrl, setRedirectUrl] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [signinLink, setSigninLink] = useState<{ url: string; expiresAt: string } | null>(null);
  const [linkError, setLinkError] = useState('');
  const [linkLoading, setLinkLoading] = useState(false);

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
    const saved = localStorage.getItem(pendingKey);
    if (!saved) return;
    try {
      const pending = JSON.parse(saved);
      if (!pending.sessionId || !pending.oauthUrl) return;
      setSessionId(pending.sessionId);
      setOauthUrl(pending.oauthUrl);
      setMarketplace(pending.marketplace ?? 'us');
      setStep('waiting');
    } catch {
      localStorage.removeItem(pendingKey);
    }
  }, [pendingKey]);

  const discardPending = () => {
    localStorage.removeItem(pendingKey);
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
        {
          method: 'POST',
          body: JSON.stringify(
            reauthId === null
              ? { marketplace, with_username: withUsername }
              : { account_id: reauthId, with_username: withUsername },
          ),
        },
      );
      setSessionId(data.session_id);
      setOauthUrl(data.oauth_url);
      localStorage.setItem(
        pendingKey,
        JSON.stringify({ sessionId: data.session_id, oauthUrl: data.oauth_url, marketplace }),
      );
      setStep('waiting');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to generate URL');
    } finally {
      setLoading(false);
    }
  };

  const createSigninLink = async () => {
    setLinkLoading(true);
    setLinkError('');
    try {
      const data = await apiFetch<{ path: string; expires_at: string }>('/signin-links', {
        method: 'POST',
        body: JSON.stringify(reauthId === null ? { marketplace } : { account_id: reauthId }),
      });
      setSigninLink({ url: `${window.location.origin}${data.path}`, expiresAt: data.expires_at });
    } catch (e) {
      setLinkError(e instanceof Error ? e.message : 'Failed to create link');
    } finally {
      setLinkLoading(false);
    }
  };

  const completeLogin = async () => {
    setLoading(true);
    setError('');
    try {
      const result = await apiFetch<CompleteResponse>('/accounts/login/complete', {
        method: 'POST',
        body: JSON.stringify({ session_id: sessionId, redirect_url: redirectUrl }),
      });
      localStorage.removeItem(pendingKey);
      navigate('/admin/accounts', { state: { notice: noticeFor(result) } });
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

      <h1 className="text-2xl font-bold text-gray-900 mb-6">
        {reauthId === null
          ? 'Add Audible Account'
          : `Re-authenticate ${reauthAccount?.username ?? 'Audible Account'}`}
      </h1>

      {reauthId !== null && (
        <Alert type="info" className="mb-4">
          This registers a new device for the account and switches it over. Sign in with the
          same Amazon account it was added with. Its books and download history stay as they
          are, and the old device stays registered until you remove it from the accounts list.
        </Alert>
      )}

      {error && <Alert type="error" className="mb-4">{error}</Alert>}

      {step === 'start' && (
        <div className="bg-white p-6 rounded-lg border border-gray-200 space-y-3 mb-4">
          <h2 className="text-base font-semibold text-gray-900">Send a sign-in link</h2>
          <p className="text-sm text-gray-600">
            For signing in someone else: send them a link. They sign in on Amazon and type a short
            code, and the account is {reauthId === null ? 'added' : 're-authenticated'} automatically.
            Nothing to send back. The link works once and expires in 7 days.
          </p>
          {linkError && <Alert type="error">{linkError}</Alert>}
          {withUsername ? (
            <p className="text-xs text-gray-500">Not available for pre-Amazon accounts; use the login URL below.</p>
          ) : signinLink ? (
            <div className="space-y-2">
              <div className="bg-gray-50 p-3 rounded text-xs font-mono break-all" data-testid="signin-link">
                {signinLink.url}
              </div>
              <div className="flex items-center gap-4">
                <button
                  type="button"
                  onClick={() => navigator.clipboard.writeText(signinLink.url)}
                  className="text-xs text-indigo-600 hover:text-indigo-800"
                >
                  Copy sign-in link
                </button>
                <span className="text-xs text-gray-400">
                  Expires {new Date(signinLink.expiresAt + 'Z').toLocaleString()}
                </span>
              </div>
            </div>
          ) : (
            <Button variant="secondary" onClick={createSigninLink} disabled={linkLoading}>
              {linkLoading ? 'Creating…' : 'Create sign-in link'}
            </Button>
          )}
        </div>
      )}

      {step === 'start' && (
        <div className="bg-white p-6 rounded-lg border border-gray-200 space-y-4">
          <h2 className="text-base font-semibold text-gray-900">Or sign in here</h2>
          {reauthId === null ? (
            <Select label="Marketplace" value={marketplace} onChange={(e) => { setMarketplace(e.target.value); setSigninLink(null); }} options={marketplaces} />
          ) : (
            <p className="text-sm text-gray-700">
              Marketplace: <span className="font-medium">{reauthAccount?.marketplace.toUpperCase() ?? '…'}</span>
            </p>
          )}
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
