import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { lastRequest, recordRequests } from '../test/record';
import { renderWithProviders } from '../test/utils';
import { LogsPage } from './LogsPage';

function makeEntry(overrides: Record<string, unknown> = {}) {
  return {
    timestamp: '2024-01-01 00:00:00',
    module: 'alima.sync',
    level: 'INFO',
    message: 'Sync started',
    ...overrides,
  };
}

function logsResponse(body: Record<string, unknown> = {}) {
  return recordRequests('get', '/api/v2/logs', {
    entries: [],
    downloads: [],
    total_downloads: 0,
    successful_downloads: 0,
    failed_downloads: 0,
    pending_downloads: 0,
    total_bytes: 0,
    average_speed_kbps: 0,
    average_duration_seconds: 0,
    downloads_by_day: [],
    top_quality: null,
    recent_failures: [],
    ...body,
  });
}

describe('LogsPage', () => {
  it('asks for the raw log view first, since that is what the tab bar shows', async () => {
    const calls = logsResponse();

    renderWithProviders(<LogsPage />);

    await waitFor(() => expect(calls.length).toBeGreaterThan(0));
    expect(calls[0].url.searchParams.get('view')).toBe('raw');
  });

  it('Refresh re-requests the logs', async () => {
    const calls = logsResponse();

    renderWithProviders(<LogsPage />);
    await waitFor(() => expect(calls).toHaveLength(1));
    await userEvent.click(screen.getByRole('button', { name: /refresh/i }));

    await waitFor(() => expect(calls.length).toBeGreaterThan(1));
  });

  it('switching to Stats requests the stats view', async () => {
    const calls = logsResponse();

    renderWithProviders(<LogsPage />);
    await userEvent.click(await screen.findByRole('button', { name: /^stats$/i }));

    await waitFor(() => expect(lastRequest(calls).url.searchParams.get('view')).toBe('stats'));
  });

  it('switching to Download History requests the downloads view', async () => {
    const calls = logsResponse();

    renderWithProviders(<LogsPage />);
    await userEvent.click(await screen.findByRole('button', { name: /download history/i }));

    await waitFor(() => expect(lastRequest(calls).url.searchParams.get('view')).toBe('downloads'));
  });

  it('sends the chosen day range on the stats view', async () => {
    const calls = logsResponse();

    renderWithProviders(<LogsPage />);
    await userEvent.click(await screen.findByRole('button', { name: /^stats$/i }));
    await userEvent.click(await screen.findByRole('button', { name: '30d' }));

    await waitFor(() => expect(lastRequest(calls).url.searchParams.get('days')).toBe('30'));
  });

  it('sends the chosen line count on the raw view', async () => {
    const calls = logsResponse();

    renderWithProviders(<LogsPage />);
    await userEvent.selectOptions(await screen.findByRole('combobox'), '2000');

    await waitFor(() => expect(lastRequest(calls).url.searchParams.get('lines')).toBe('2000'));
  });

  it('offers a line count only on the raw view, and a range only on the others', async () => {
    logsResponse();

    renderWithProviders(<LogsPage />);
    expect(await screen.findByRole('combobox')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '30d' })).toBeNull();

    await userEvent.click(screen.getByRole('button', { name: /^stats$/i }));
    expect(await screen.findByRole('button', { name: '30d' })).toBeInTheDocument();
    expect(screen.queryByRole('combobox')).toBeNull();
  });

  it('hides entries below the selected level', async () => {
    logsResponse({
      entries: [
        makeEntry({ level: 'INFO', message: 'Sync started' }),
        makeEntry({ level: 'ERROR', message: 'Download exploded' }),
      ],
    });

    renderWithProviders(<LogsPage />);
    await screen.findByText('Sync started');
    await userEvent.click(screen.getByRole('button', { name: /errors only/i }));

    expect(screen.getByText('Download exploded')).toBeInTheDocument();
    expect(screen.queryByText('Sync started')).toBeNull();
  });

  it('shows everything, DEBUG included, on the All filter', async () => {
    logsResponse({
      entries: [makeEntry({ level: 'DEBUG', message: 'Cache hit' })],
    });

    renderWithProviders(<LogsPage />);
    // DEBUG sits below the default INFO threshold, so it starts out hidden.
    const allFilter = await screen.findByRole('button', { name: /^all$/i });
    expect(screen.queryByText('Cache hit')).toBeNull();
    await userEvent.click(allFilter);

    expect(await screen.findByText('Cache hit')).toBeInTheDocument();
  });

  it('says the level is empty rather than showing a blank pane', async () => {
    logsResponse({ entries: [makeEntry({ level: 'INFO' })] });

    renderWithProviders(<LogsPage />);
    await screen.findByText('Sync started');
    await userEvent.click(screen.getByRole('button', { name: /errors only/i }));

    expect(screen.getByText(/no entries at this level/i)).toBeInTheDocument();
  });

  it('renders the download history table', async () => {
    logsResponse({
      downloads: [{
        id: 1, asin: 'B01', book_title: 'The Hobbit', status: 'completed',
        file_size_bytes: 1024, duration_seconds: 90, download_speed_kbps: 2048,
        download_quality: 'high', attempts: 1, error_message: null,
        created_at: '2024-01-01T00:00:00', completed_at: '2024-01-01T00:10:00',
      }],
    });

    renderWithProviders(<LogsPage />);
    await userEvent.click(await screen.findByRole('button', { name: /download history/i }));

    expect(await screen.findByText('The Hobbit')).toBeInTheDocument();
  });

  it('says the range is empty rather than showing a headerless table', async () => {
    logsResponse({ downloads: [] });

    renderWithProviders(<LogsPage />);
    await userEvent.click(await screen.findByRole('button', { name: /download history/i }));

    expect(await screen.findByText(/no downloads in this time range/i)).toBeInTheDocument();
  });

  it('renders the download statistics', async () => {
    logsResponse({
      total_downloads: 10, successful_downloads: 8, failed_downloads: 2,
      downloads_by_day: [{ date: '2024-01-01', count: 4 }],
      recent_failures: [{
        asin: 'B01', book_title: 'Dune',
        created_at: '2024-01-01T00:00:00', error_message: 'timeout',
      }],
    });

    renderWithProviders(<LogsPage />);
    await userEvent.click(await screen.findByRole('button', { name: /^stats$/i }));

    expect(await screen.findByText('10')).toBeInTheDocument();
    expect(screen.getByText('Dune')).toBeInTheDocument();
    expect(screen.getByText('timeout')).toBeInTheDocument();
  });
});
