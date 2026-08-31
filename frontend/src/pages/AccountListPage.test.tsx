import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { recordRequests, stubConfirm } from '../test/record';
import { server } from '../test/server';
import { attachFile, renderWithProviders } from '../test/utils';
import { AccountListPage } from './AccountListPage';

function makeAccount(overrides: Record<string, unknown> = {}) {
  return {
    id: 2,
    username: 'reader@example.com',
    marketplace: 'us',
    enabled: true,
    downloads_enabled: true,
    last_sync_timestamp: '2024-01-01T00:00:00',
    ...overrides,
  };
}

function showAccounts(...accounts: unknown[]) {
  server.use(http.get('/api/v2/accounts', () => HttpResponse.json({ accounts })));
}

describe('AccountListPage', () => {
  it('Sync posts to that account only', async () => {
    showAccounts(makeAccount({ id: 2 }), makeAccount({ id: 3, username: 'other@example.com' }));
    const calls = recordRequests('post', '/api/v2/accounts/2/sync', { job_id: 1 });

    renderWithProviders(<AccountListPage />);
    await userEvent.click((await screen.findAllByRole('button', { name: 'Sync' }))[0]);

    await waitFor(() => expect(calls).toHaveLength(1));
  });

  it('Queue All posts to the queue-all endpoint', async () => {
    showAccounts(makeAccount({ id: 2 }));
    const calls = recordRequests('post', '/api/v2/accounts/2/queue-all');

    renderWithProviders(<AccountListPage />);
    await userEvent.click(await screen.findByRole('button', { name: /queue all/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
  });

  it('Disable patches enabled false', async () => {
    showAccounts(makeAccount({ id: 2, enabled: true }));
    const calls = recordRequests('patch', '/api/v2/accounts/2');

    renderWithProviders(<AccountListPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Disable' }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toEqual({ enabled: false });
  });

  it('Enable patches enabled true', async () => {
    showAccounts(makeAccount({ id: 2, enabled: false }));
    const calls = recordRequests('patch', '/api/v2/accounts/2');

    renderWithProviders(<AccountListPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Enable' }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toEqual({ enabled: true });
  });

  it('Stop DL toggles downloads_enabled, not enabled', async () => {
    // The two flags sit next to each other and are easy to cross-wire; doing
    // so would disable the whole account when the user only wanted to pause
    // downloads.
    showAccounts(makeAccount({ id: 2, downloads_enabled: true }));
    const calls = recordRequests('patch', '/api/v2/accounts/2');

    renderWithProviders(<AccountListPage />);
    await userEvent.click(await screen.findByRole('button', { name: /stop dl/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toEqual({ downloads_enabled: false });
  });

  it('Start DL toggles downloads_enabled back on', async () => {
    showAccounts(makeAccount({ id: 2, downloads_enabled: false }));
    const calls = recordRequests('patch', '/api/v2/accounts/2');

    renderWithProviders(<AccountListPage />);
    await userEvent.click(await screen.findByRole('button', { name: /start dl/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toEqual({ downloads_enabled: true });
  });

  it('Delete names the account and deletes on confirm', async () => {
    showAccounts(makeAccount({ id: 2, username: 'reader@example.com' }));
    const confirm = stubConfirm(true);
    const calls = recordRequests('delete', '/api/v2/accounts/2');

    renderWithProviders(<AccountListPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Delete' }));

    expect(confirm).toHaveBeenCalledWith(expect.stringContaining('reader@example.com'));
    await waitFor(() => expect(calls).toHaveLength(1));
  });

  it('does not delete when the confirmation is dismissed', async () => {
    showAccounts(makeAccount({ id: 2 }));
    stubConfirm(false);
    const calls = recordRequests('delete', '/api/v2/accounts/2');

    renderWithProviders(<AccountListPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Delete' }));

    expect(calls).toHaveLength(0);
  });

  it('Force Refresh Metadata kicks off the sync job', async () => {
    showAccounts(makeAccount());
    const calls = recordRequests('post', '/api/v2/sync/force-refresh-metadata', { job_id: 8 });

    renderWithProviders(<AccountListPage />);
    await userEvent.click(await screen.findByRole('button', { name: /force refresh metadata/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
  });

  it('uploads the auth file with the username and marketplace', async () => {
    // An account is listed so the empty state -- which offers its own "Add
    // Account" -- stays out of the way of the form's submit button.
    showAccounts(makeAccount());
    const calls = recordRequests('post', '/api/v2/accounts', { id: 3 });

    renderWithProviders(<AccountListPage />);
    await userEvent.click(await screen.findByRole('button', { name: /upload auth file/i }));
    await userEvent.type(screen.getByLabelText(/username/i), 'reader@example.com');
    await userEvent.selectOptions(screen.getByLabelText(/marketplace/i), 'DE');
    attachFile(
      screen.getByLabelText(/auth file/i),
      new File(['{}'], 'auth.json', { type: 'application/json' }),
    );
    // Submitted directly rather than by clicking: the file input is `required`
    // and jsdom's constraint validation does not see a file list installed by
    // attachFile, so a click would be swallowed before the handler ran.
    fireEvent.submit(screen.getByRole('button', { name: /add account/i }).closest('form')!);

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body.username).toBe('reader@example.com');
    expect(calls[0].body.marketplace).toBe('DE');
    expect(calls[0].headers.get('content-type')).toMatch(/multipart\/form-data/);
  });

  it('does not upload without a file, even with the username filled in', async () => {
    showAccounts(makeAccount());
    const calls = recordRequests('post', '/api/v2/accounts', { id: 3 });

    renderWithProviders(<AccountListPage />);
    await userEvent.click(await screen.findByRole('button', { name: /upload auth file/i }));
    await userEvent.type(screen.getByLabelText(/username/i), 'reader@example.com');
    await userEvent.click(screen.getByRole('button', { name: /add account/i }));

    expect(calls).toHaveLength(0);
  });

  it('surfaces a rejected upload instead of silently closing the form', async () => {
    showAccounts(makeAccount());
    recordRequests('post', '/api/v2/accounts', { detail: 'Invalid auth file' }, { status: 400 });

    renderWithProviders(<AccountListPage />);
    await userEvent.click(await screen.findByRole('button', { name: /upload auth file/i }));
    await userEvent.type(screen.getByLabelText(/username/i), 'reader@example.com');
    attachFile(
      screen.getByLabelText(/auth file/i),
      new File(['nope'], 'auth.json', { type: 'application/json' }),
    );
    fireEvent.submit(screen.getByRole('button', { name: /add account/i }).closest('form')!);

    expect(await screen.findByText(/invalid auth file/i)).toBeInTheDocument();
  });

  it('shows an empty state when no account is connected', async () => {
    showAccounts();
    renderWithProviders(<AccountListPage />);

    expect(await screen.findByText(/no accounts/i)).toBeInTheDocument();
  });
});
