import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { recordRequests } from '../test/record';
import { server } from '../test/server';
import { renderWithProviders } from '../test/utils';
import { SettingsPage } from './SettingsPage';

function showSettings(settings: Record<string, string | null> = {}) {
  server.use(
    http.get('/api/v2/settings', () =>
      HttpResponse.json({
        settings: {
          app_name: 'Alima',
          domain: 'example.com',
          smtp_host: 'smtp.example.com',
          b2_enabled: 'false',
          default_feed_cover_url: null,
          ...settings,
        },
      }),
    ),
  );
}

describe('SettingsPage', () => {
  it('prefills the form from the saved settings', async () => {
    showSettings({ app_name: 'My Library' });
    renderWithProviders(<SettingsPage />);

    expect(await screen.findByLabelText(/app name/i)).toHaveValue('My Library');
  });

  it('renders a null setting as an empty field rather than the string "null"', async () => {
    showSettings({ domain: null });
    renderWithProviders(<SettingsPage />);

    expect(await screen.findByLabelText(/domain/i)).toHaveValue('');
  });

  it('Save Settings PUTs the edited values', async () => {
    showSettings({ app_name: 'Alima' });
    const calls = recordRequests('put', '/api/v2/settings');

    renderWithProviders(<SettingsPage />);
    const appName = await screen.findByLabelText(/app name/i);
    await userEvent.clear(appName);
    await userEvent.type(appName, 'My Library');
    await userEvent.click(screen.getByRole('button', { name: /save settings/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body.app_name).toBe('My Library');
    expect(await screen.findByText(/settings saved/i)).toBeInTheDocument();
  });

  it('surfaces a rejected save instead of claiming success', async () => {
    showSettings();
    recordRequests('put', '/api/v2/settings', { detail: 'Invalid SMTP port' }, { status: 400 });

    renderWithProviders(<SettingsPage />);
    await userEvent.click(await screen.findByRole('button', { name: /save settings/i }));

    expect(await screen.findByText(/invalid smtp port/i)).toBeInTheDocument();
    expect(screen.queryByText(/settings saved/i)).toBeNull();
  });

  it('Send Test posts the recipient address', async () => {
    showSettings();
    const calls = recordRequests('post', '/api/v2/settings/test-email');

    renderWithProviders(<SettingsPage />);
    await userEvent.type(await screen.findByLabelText(/test email/i), 'me@example.com');
    await userEvent.click(screen.getByRole('button', { name: /send test/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toEqual({ recipient_email: 'me@example.com' });
    expect(await screen.findByText(/test email sent/i)).toBeInTheDocument();
  });

  it('will not send a test email with no address to send it to', async () => {
    showSettings();
    renderWithProviders(<SettingsPage />);

    expect(await screen.findByRole('button', { name: /send test/i })).toBeDisabled();
  });

  it('reports an SMTP failure rather than a false success', async () => {
    // This button exists precisely to find out whether SMTP works; a silent
    // failure defeats its whole purpose.
    showSettings();
    recordRequests('post', '/api/v2/settings/test-email', { detail: 'Auth failed' }, { status: 500 });

    renderWithProviders(<SettingsPage />);
    await userEvent.type(await screen.findByLabelText(/test email/i), 'me@example.com');
    await userEvent.click(screen.getByRole('button', { name: /send test/i }));

    expect(await screen.findByText(/auth failed/i)).toBeInTheDocument();
  });

  it('Test Connection posts to the B2 endpoint', async () => {
    showSettings({ b2_enabled: 'true' });
    const calls = recordRequests('post', '/api/v2/settings/test-b2');

    renderWithProviders(<SettingsPage />);
    await userEvent.click(await screen.findByRole('button', { name: /test connection/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(await screen.findByText(/connected to b2/i)).toBeInTheDocument();
  });

  it('reports a failed B2 connection', async () => {
    showSettings({ b2_enabled: 'true' });
    recordRequests('post', '/api/v2/settings/test-b2', { detail: 'Bad bucket' }, { status: 500 });

    renderWithProviders(<SettingsPage />);
    await userEvent.click(await screen.findByRole('button', { name: /test connection/i }));

    expect(await screen.findByText(/bad bucket/i)).toBeInTheDocument();
  });

  it('hides the B2 fields until B2 is enabled', async () => {
    showSettings({ b2_enabled: 'false' });
    renderWithProviders(<SettingsPage />);

    await screen.findByLabelText(/app name/i);
    expect(screen.queryByLabelText(/bucket name/i)).toBeNull();
    expect(screen.queryByRole('button', { name: /test connection/i })).toBeNull();
  });

  it('reveals the B2 fields when it is switched on', async () => {
    showSettings({ b2_enabled: 'false' });
    renderWithProviders(<SettingsPage />);

    await userEvent.selectOptions(await screen.findByLabelText(/enable b2 storage/i), 'true');

    expect(await screen.findByLabelText(/bucket name/i)).toBeInTheDocument();
  });

  it('Remove deletes the default cover, and only shows when one is set', async () => {
    showSettings({ default_feed_cover_url: 'https://example.com/cover.jpg' });
    const calls = recordRequests('delete', '/api/v2/settings/default-cover');

    renderWithProviders(<SettingsPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Remove' }));

    await waitFor(() => expect(calls).toHaveLength(1));
  });

  it('offers nothing to remove when no default cover is set', async () => {
    showSettings({ default_feed_cover_url: null });
    renderWithProviders(<SettingsPage />);

    expect(await screen.findByText(/no default cover set/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Remove' })).toBeNull();
  });
});
