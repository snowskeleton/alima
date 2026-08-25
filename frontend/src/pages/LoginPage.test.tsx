import userEvent from '@testing-library/user-event';
import { screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { server } from '../test/server';
import { renderWithProviders } from '../test/utils';
import { LoginPage } from './LoginPage';

/** Anonymous auth status, since this page is only reached logged out. */
function anonymous(overrides: Record<string, unknown> = {}) {
  return http.get('/api/v2/auth/status', () =>
    HttpResponse.json({
      authenticated: false,
      user: null,
      needs_registration: false,
      ...overrides,
    }),
  );
}

describe('LoginPage', () => {
  it('renders the email form', async () => {
    server.use(anonymous());
    renderWithProviders(<LoginPage />);

    expect(await screen.findByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /magic link/i })).toBeInTheDocument();
  });

  it('never asks for a password', async () => {
    // Auth is magic-link only. A password field here would mean the old
    // password flow had crept back in.
    server.use(anonymous());
    renderWithProviders(<LoginPage />);

    await screen.findByLabelText(/email/i);
    expect(document.querySelector('input[type="password"]')).toBeNull();
  });

  it('posts the typed email to the login endpoint', async () => {
    let body: unknown = null;
    server.use(
      anonymous(),
      http.post('/api/v2/auth/login', async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ sent: true });
      }),
    );

    renderWithProviders(<LoginPage />);
    await userEvent.type(await screen.findByLabelText(/email/i), 'me@example.com');
    await userEvent.click(screen.getByRole('button', { name: /magic link/i }));

    await waitFor(() => expect(body).toEqual({ email: 'me@example.com' }));
  });

  it('shows an error when sending the link fails', async () => {
    server.use(
      anonymous(),
      http.post('/api/v2/auth/login', () =>
        HttpResponse.json({ detail: 'SMTP down' }, { status: 500 }),
      ),
    );

    renderWithProviders(<LoginPage />);
    await userEvent.type(await screen.findByLabelText(/email/i), 'me@example.com');
    await userEvent.click(screen.getByRole('button', { name: /magic link/i }));

    expect(await screen.findByText(/failed to send login link/i)).toBeInTheDocument();
  });

  it('redirects an already-authenticated visitor to the library', async () => {
    server.use(
      http.get('/api/v2/auth/status', () =>
        HttpResponse.json({
          authenticated: true,
          user: { id: 1, email: 'a@b.c', role: 'user' },
          needs_registration: false,
        }),
      ),
    );

    renderWithProviders(<LoginPage />);

    // The form is replaced by a <Navigate>, so it must not be reachable.
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /magic link/i })).toBeNull(),
    );
  });

  it('redirects to register when the instance has no users yet', async () => {
    server.use(anonymous({ needs_registration: true }));
    renderWithProviders(<LoginPage />);

    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /magic link/i })).toBeNull(),
    );
  });
});
