import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { adminUser } from '../test/handlers';
import { recordRequests } from '../test/record';
import { server } from '../test/server';
import { currentPath, renderWithProviders } from '../test/utils';
import { RegisterPage } from './RegisterPage';

function authStatus(status: Record<string, unknown>) {
  server.use(http.get('/api/v2/auth/status', () => HttpResponse.json(status)));
}

function render(auth: unknown) {
  return renderWithProviders(<RegisterPage />, {
    route: '/auth/register',
    path: '/auth/register',
    auth,
  });
}

describe('RegisterPage', () => {
  it('registers the first admin and lands them in the library', async () => {
    const status = { authenticated: false, user: null, needs_registration: true };
    authStatus(status);
    const calls = recordRequests('post', '/api/v2/auth/register', { ok: true });

    render(status);
    await userEvent.type(await screen.findByLabelText(/email/i), 'admin@example.com');
    await userEvent.click(screen.getByRole('button', { name: /create admin account/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toEqual({ email: 'admin@example.com' });
    await waitFor(() => expect(currentPath()).toBe('/library'));
  });

  it('says registration failed rather than silently doing nothing', async () => {
    const status = { authenticated: false, user: null, needs_registration: true };
    authStatus(status);
    recordRequests('post', '/api/v2/auth/register', { detail: 'taken' }, { status: 400 });

    render(status);
    await userEvent.type(await screen.findByLabelText(/email/i), 'admin@example.com');
    await userEvent.click(screen.getByRole('button', { name: /create admin account/i }));

    expect(await screen.findByText(/registration failed/i)).toBeInTheDocument();
    expect(currentPath()).toBe('/auth/register');
  });

  it('sends nobody to registration once an admin exists', async () => {
    // The endpoint only accepts the very first user; leaving this page reachable
    // would offer everyone else a button that can only fail.
    const status = { authenticated: false, user: null, needs_registration: false };
    authStatus(status);

    render(status);

    await waitFor(() => expect(currentPath()).toBe('/auth/login'));
  });

  it('sends an already-signed-in user to the library', async () => {
    const status = { authenticated: true, user: adminUser, needs_registration: false };
    authStatus(status);

    render(status);

    await waitFor(() => expect(currentPath()).toBe('/library'));
  });
});
