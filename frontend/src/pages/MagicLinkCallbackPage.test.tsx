import { screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { recordRequests } from '../test/record';
import { currentPath, renderWithProviders } from '../test/utils';
import { MagicLinkCallbackPage } from './MagicLinkCallbackPage';

function render(search: string) {
  return renderWithProviders(<MagicLinkCallbackPage />, {
    route: `/auth/magic-link${search}`,
    path: '/auth/magic-link',
  });
}

describe('MagicLinkCallbackPage', () => {
  it('exchanges the token and sends the user to the library', async () => {
    const calls = recordRequests('get', '/api/v2/auth/magic-link', { ok: true });

    render('?token=abc123');

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].url.searchParams.get('token')).toBe('abc123');
    await waitFor(() => expect(currentPath()).toBe('/library'));
  });

  it('escapes a token containing URL-significant characters', async () => {
    // Tokens are base64url but have carried padding before; an unescaped '+'
    // would arrive as a space and the link would look expired.
    const calls = recordRequests('get', '/api/v2/auth/magic-link', { ok: true });

    render(`?token=${encodeURIComponent('a+b/c=')}`);

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].url.searchParams.get('token')).toBe('a+b/c=');
  });

  it('explains an expired link instead of a blank page', async () => {
    recordRequests(
      'get', '/api/v2/auth/magic-link',
      { detail: 'Invalid or expired magic link' }, { status: 400 },
    );

    render('?token=stale');

    expect(await screen.findByText(/invalid or expired/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /back to login/i })).toBeInTheDocument();
  });

  it('says so when the link arrived with no token at all', async () => {
    render('');

    expect(await screen.findByText(/no token provided/i)).toBeInTheDocument();
  });
});
