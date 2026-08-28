import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it, vi } from 'vitest';
import { recordRequests, stubConfirm } from '../test/record';
import { server } from '../test/server';
import { inModal, renderWithProviders } from '../test/utils';
import { ApiKeyPage } from './ApiKeyPage';

function makeKey(overrides: Record<string, unknown> = {}) {
  return {
    id: 4,
    name: 'My Script',
    key_prefix: 'alima_ab12',
    is_expired: false,
    created_at: '2024-01-01T00:00:00',
    last_used_at: null,
    expires_at: null,
    ...overrides,
  };
}

function showKeys(...api_keys: unknown[]) {
  server.use(http.get('/api/v2/api-keys', () => HttpResponse.json({ api_keys })));
}

/** The page header and the empty state both offer "Create Key"; either opens
 * the same modal, so the first one on screen will do. */
async function openCreateForm() {
  await userEvent.click((await screen.findAllByRole('button', { name: /create key/i }))[0]);
}

describe('ApiKeyPage', () => {
  it('creates a key with the name given', async () => {
    showKeys();
    const calls = recordRequests('post', '/api/v2/api-keys', { key: 'alima_secret', key_id: 4 });

    renderWithProviders(<ApiKeyPage />);
    await openCreateForm();
    await userEvent.type(inModal().getByLabelText(/key name/i), 'CI');
    await userEvent.click(inModal().getByRole('button', { name: /^create key$/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toEqual({ name: 'CI' });
  });

  it('sends expires_in_days when an expiry was entered', async () => {
    showKeys();
    const calls = recordRequests('post', '/api/v2/api-keys', { key: 'alima_secret', key_id: 4 });

    renderWithProviders(<ApiKeyPage />);
    await openCreateForm();
    await userEvent.type(inModal().getByLabelText(/key name/i), 'CI');
    await userEvent.type(inModal().getByLabelText(/expires in/i), '30');
    await userEvent.click(inModal().getByRole('button', { name: /^create key$/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toEqual({ name: 'CI', expires_in_days: 30 });
  });

  it('omits expires_in_days entirely when the field is blank', async () => {
    // Sending null or 0 here would be read as "already expired" rather than
    // "never expires", locking the user out of the key they just made.
    showKeys();
    const calls = recordRequests('post', '/api/v2/api-keys', { key: 'alima_secret', key_id: 4 });

    renderWithProviders(<ApiKeyPage />);
    await openCreateForm();
    await userEvent.type(inModal().getByLabelText(/key name/i), 'CI');
    await userEvent.click(inModal().getByRole('button', { name: /^create key$/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).not.toHaveProperty('expires_in_days');
  });

  it('shows the new key once, since the backend never returns it again', async () => {
    showKeys();
    recordRequests('post', '/api/v2/api-keys', { key: 'alima_supersecret', key_id: 4 });

    renderWithProviders(<ApiKeyPage />);
    await openCreateForm();
    await userEvent.type(inModal().getByLabelText(/key name/i), 'CI');
    await userEvent.click(inModal().getByRole('button', { name: /^create key$/i }));

    expect(await screen.findByText('alima_supersecret')).toBeInTheDocument();
  });

  it('copies the new key to the clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    showKeys();
    recordRequests('post', '/api/v2/api-keys', { key: 'alima_supersecret', key_id: 4 });

    renderWithProviders(<ApiKeyPage />);
    await openCreateForm();
    await userEvent.type(inModal().getByLabelText(/key name/i), 'CI');
    await userEvent.click(inModal().getByRole('button', { name: /^create key$/i }));
    await userEvent.click(await screen.findByRole('button', { name: /copy to clipboard/i }));

    expect(writeText).toHaveBeenCalledWith('alima_supersecret');
  });

  it('Delete names the key and deletes it on confirm', async () => {
    showKeys(makeKey({ id: 4, name: 'My Script' }));
    const confirm = stubConfirm(true);
    const calls = recordRequests('delete', '/api/v2/api-keys/4');

    renderWithProviders(<ApiKeyPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Delete' }));

    expect(confirm).toHaveBeenCalledWith(expect.stringContaining('My Script'));
    await waitFor(() => expect(calls).toHaveLength(1));
  });

  it('does not delete when the confirmation is dismissed', async () => {
    showKeys(makeKey({ id: 4 }));
    stubConfirm(false);
    const calls = recordRequests('delete', '/api/v2/api-keys/4');

    renderWithProviders(<ApiKeyPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Delete' }));

    expect(calls).toHaveLength(0);
  });

  it('marks an expired key so it is not mistaken for a working one', async () => {
    showKeys(makeKey({ is_expired: true }));
    renderWithProviders(<ApiKeyPage />);

    expect(await screen.findByText(/expired/i)).toBeInTheDocument();
  });
});
