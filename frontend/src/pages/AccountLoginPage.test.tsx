import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { recordRequests } from '../test/record';
import { currentPath, renderWithProviders } from '../test/utils';
import { AccountLoginPage } from './AccountLoginPage';

const PENDING_KEY = 'alima.pendingAudibleLogin';

afterEach(() => localStorage.clear());

function render() {
  return renderWithProviders(<AccountLoginPage />, {
    route: '/admin/accounts/login',
    path: '/admin/accounts/login',
  });
}

describe('AccountLoginPage', () => {
  it('Generate Login URL posts the marketplace and moves to the waiting step', async () => {
    const calls = recordRequests('post', '/api/v2/accounts/login/generate-url', {
      session_id: 'sess-1',
      oauth_url: 'https://amazon.example/oauth?state=abc',
    });

    render();
    await userEvent.selectOptions(screen.getByLabelText(/marketplace/i), 'de');
    await userEvent.click(screen.getByRole('button', { name: /generate login url/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toEqual({ marketplace: 'de', with_username: false });
    expect(await screen.findByPlaceholderText(/redirect url/i)).toBeInTheDocument();
  });

  it('passes with_username for a pre-Amazon account', async () => {
    const calls = recordRequests('post', '/api/v2/accounts/login/generate-url', {
      session_id: 'sess-1', oauth_url: 'https://amazon.example/oauth',
    });

    render();
    await userEvent.click(screen.getByRole('checkbox'));
    await userEvent.click(screen.getByRole('button', { name: /generate login url/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body.with_username).toBe(true);
  });

  it('stays on the first step and explains why when the URL cannot be generated', async () => {
    recordRequests(
      'post', '/api/v2/accounts/login/generate-url',
      { detail: 'Marketplace unavailable' }, { status: 400 },
    );

    render();
    await userEvent.click(screen.getByRole('button', { name: /generate login url/i }));

    expect(await screen.findByText(/marketplace unavailable/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /generate login url/i })).toBeInTheDocument();
  });

  it('Complete Login posts the session and the pasted redirect URL', async () => {
    recordRequests('post', '/api/v2/accounts/login/generate-url', {
      session_id: 'sess-1', oauth_url: 'https://amazon.example/oauth',
    });
    const calls = recordRequests('post', '/api/v2/accounts/login/complete');

    render();
    await userEvent.click(screen.getByRole('button', { name: /generate login url/i }));
    await userEvent.type(
      await screen.findByPlaceholderText(/redirect url/i),
      'https://amazon.example/done?code=xyz',
    );
    await userEvent.click(screen.getByRole('button', { name: /complete login/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toEqual({
      session_id: 'sess-1',
      redirect_url: 'https://amazon.example/done?code=xyz',
    });
    await waitFor(() => expect(currentPath()).toBe('/admin/accounts'));
  });

  it('will not complete a login with nothing pasted in', async () => {
    recordRequests('post', '/api/v2/accounts/login/generate-url', {
      session_id: 'sess-1', oauth_url: 'https://amazon.example/oauth',
    });

    render();
    await userEvent.click(screen.getByRole('button', { name: /generate login url/i }));

    expect(await screen.findByRole('button', { name: /complete login/i })).toBeDisabled();
  });

  it('keeps the pending login on screen when completing fails', async () => {
    // The OAuth redirect URL is single-use and awkward to obtain again, so
    // dropping back to the start step on a failure would strand the user.
    recordRequests('post', '/api/v2/accounts/login/generate-url', {
      session_id: 'sess-1', oauth_url: 'https://amazon.example/oauth',
    });
    recordRequests('post', '/api/v2/accounts/login/complete', { detail: 'Expired' }, { status: 400 });

    render();
    await userEvent.click(screen.getByRole('button', { name: /generate login url/i }));
    await userEvent.type(await screen.findByPlaceholderText(/redirect url/i), 'https://x');
    await userEvent.click(screen.getByRole('button', { name: /complete login/i }));

    expect(await screen.findByText(/expired/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /complete login/i })).toBeInTheDocument();
  });

  it('resumes a pending login saved by an earlier visit', async () => {
    // The whole point of the saved session is that the page can be closed
    // while waiting for the account's owner to sign in.
    localStorage.setItem(
      PENDING_KEY,
      JSON.stringify({ sessionId: 'sess-1', oauthUrl: 'https://amazon.example/oauth', marketplace: 'de' }),
    );

    render();

    expect(await screen.findByPlaceholderText(/redirect url/i)).toBeInTheDocument();
  });

  it('ignores a corrupt saved session rather than getting stuck on it', async () => {
    localStorage.setItem(PENDING_KEY, 'not json');

    render();

    expect(await screen.findByRole('button', { name: /generate login url/i })).toBeInTheDocument();
    expect(localStorage.getItem(PENDING_KEY)).toBeNull();
  });

  it('Start over clears the saved session', async () => {
    localStorage.setItem(
      PENDING_KEY,
      JSON.stringify({ sessionId: 'sess-1', oauthUrl: 'https://amazon.example/oauth' }),
    );

    render();
    await userEvent.click(await screen.findByRole('button', { name: /start over/i }));

    expect(localStorage.getItem(PENDING_KEY)).toBeNull();
    expect(screen.getByRole('button', { name: /generate login url/i })).toBeInTheDocument();
  });

  it('copies the login URL so it can be sent to the account owner', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    localStorage.setItem(
      PENDING_KEY,
      JSON.stringify({ sessionId: 'sess-1', oauthUrl: 'https://amazon.example/oauth' }),
    );

    render();
    await userEvent.click(await screen.findByRole('button', { name: /copy login url/i }));

    expect(writeText).toHaveBeenCalledWith('https://amazon.example/oauth');
  });
});
