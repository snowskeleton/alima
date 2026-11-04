import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { apiFetch } from '../api/client';
import { Alert } from '../components/ui/Alert';
import { Button } from '../components/ui/Button';

/** What the server says about a sign-in link. See app/routers/api_v2/signin_links.py. */
export interface SigninLinkState {
  status: 'ready' | 'waiting' | 'done' | 'expired';
  marketplace: string;
  code_url: string;
  reauth: boolean;
  account_name: string | null;
  code?: string;
  code_expires_in?: number;
  poll_interval?: number;
  code_expired?: boolean;
  username?: string | null;
}

function formatRemaining(seconds: number) {
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

/**
 * Public page an Audible account's owner opens from a link the admin sent.
 * No Alima login: the token in the URL is the credential. They sign in on
 * Amazon's own site and type a short code; this page notices on its own.
 */
export function SignInLinkPage() {
  const { token = '' } = useParams();
  const base = `/signin-links/${encodeURIComponent(token)}`;
  const [state, setState] = useState<SigninLinkState | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [deadline, setDeadline] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());

  const apply = useCallback((next: SigninLinkState) => {
    setState(next);
    setDeadline(
      next.status === 'waiting' && next.code_expires_in != null
        ? Date.now() + next.code_expires_in * 1000
        : null,
    );
  }, []);

  const refresh = useCallback(async () => {
    try {
      apply(await apiFetch<SigninLinkState>(base));
    } catch (e) {
      if ((e as { status?: number }).status === 404) setNotFound(true);
      else setError(e instanceof Error ? e.message : 'Something went wrong');
    }
  }, [apply, base]);

  useEffect(() => { refresh(); }, [refresh]);

  // Poll while a code is on screen. The server only asks Amazon at Amazon's
  // own pace, so polling a little faster just makes the page react sooner.
  const waiting = state?.status === 'waiting';
  const interval = Math.max(2, state?.poll_interval ?? 5) * 1000;
  useEffect(() => {
    if (!waiting) return;
    const id = window.setInterval(async () => {
      try {
        apply(await apiFetch<SigninLinkState>(`${base}/poll`, { method: 'POST' }));
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Something went wrong');
        refresh();
      }
    }, interval);
    return () => window.clearInterval(id);
  }, [waiting, interval, base, apply, refresh]);

  // Countdown; when the code runs out, ask the server what to show next.
  useEffect(() => {
    if (deadline === null) return;
    const id = window.setInterval(() => {
      setNow(Date.now());
      if (Date.now() >= deadline) refresh();
    }, 1000);
    return () => window.clearInterval(id);
  }, [deadline, refresh]);

  const getCode = async () => {
    setBusy(true);
    setError('');
    try {
      apply(await apiFetch<SigninLinkState>(`${base}/code`, { method: 'POST' }));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not get a code');
    } finally {
      setBusy(false);
    }
  };

  const title = state?.reauth ? 'Reconnect your Audible account' : 'Connect your Audible account';
  const codeHost = state ? new URL(state.code_url).host.replace(/^www\./, '') + '/code' : '';

  let body: React.ReactNode;
  if (notFound) {
    body = <Alert type="error">This sign-in link isn’t valid. Ask the person who sent it for a new one.</Alert>;
  } else if (!state) {
    body = <p className="text-sm text-gray-500 text-center">Loading…</p>;
  } else if (state.status === 'done') {
    body = (
      <Alert type="success">
        All set{state.username ? `, ${state.username}` : ''}! Your Audible account is connected. You can close this page.
      </Alert>
    );
  } else if (state.status === 'expired') {
    body = <Alert type="warning">This sign-in link has expired. Ask the person who sent it for a new one.</Alert>;
  } else if (state.status === 'waiting') {
    body = (
      <div className="space-y-5">
        <div>
          <p className="text-sm text-gray-700 mb-2">
            <span className="font-medium">1.</span> Open Amazon’s code page and sign in with the Amazon
            account you use for Audible{state.account_name ? ` (${state.account_name})` : ''}.
          </p>
          <a href={state.code_url} target="_blank" rel="noopener noreferrer">
            <Button className="w-full">Open {codeHost}</Button>
          </a>
        </div>
        <div>
          <p className="text-sm text-gray-700 mb-2"><span className="font-medium">2.</span> Enter this code:</p>
          <p
            className="text-center font-mono text-4xl font-bold tracking-[0.3em] text-gray-900 bg-gray-50 border border-gray-200 rounded-lg py-4"
            aria-label="Your code"
          >
            {state.code}
          </p>
          {deadline !== null && (
            <p className="mt-2 text-xs text-gray-500 text-center">
              Valid for {formatRemaining((deadline - now) / 1000)}
            </p>
          )}
        </div>
        <p className="text-sm text-gray-500 text-center" role="status">
          Waiting for you to enter the code… this page updates by itself.
        </p>
      </div>
    );
  } else {
    body = (
      <div className="space-y-4">
        {state.code_expired && (
          <Alert type="info">That code ran out before it was entered. Get a new one below.</Alert>
        )}
        <p className="text-sm text-gray-700">
          This takes about a minute. You’ll sign in on Amazon’s own website, so this site never sees your
          password. Then you’ll type a short code there.
        </p>
        <Button className="w-full" onClick={getCode} disabled={busy}>
          {busy ? 'Getting a code…' : 'Get my code'}
        </Button>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="max-w-sm w-full bg-white border border-gray-200 rounded-lg p-6">
        <h1 className="text-xl font-bold text-gray-900 mb-1">{title}</h1>
        <p className="text-sm text-gray-500 mb-5">for Alima, an audiobook library</p>
        {error && <Alert type="error" className="mb-4">{error}</Alert>}
        {body}
      </div>
    </div>
  );
}
