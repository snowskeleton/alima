import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { lastRequest, recordRequests, stubConfirm } from '../test/record';
import { server } from '../test/server';
import { renderWithProviders } from '../test/utils';
import { DownloadQueuePage } from './DownloadQueuePage';

function makeEntry(overrides: Record<string, unknown> = {}) {
  return {
    id: 11,
    asin: 'B000000001',
    book_title: 'The Hobbit',
    book_author: 'J.R.R. Tolkien',
    account_username: 'reader@example.com',
    status: 'pending',
    stalled: false,
    read: false,
    attempts: 1,
    bytes_downloaded: null,
    total_bytes: null,
    eta_seconds: null,
    idle_seconds: null,
    file_size_bytes: null,
    download_speed_kbps: null,
    download_quality: null,
    duration_seconds: null,
    error_message: null,
    created_at: '2024-01-01T00:00:00',
    ...overrides,
  };
}

function makeStats(overrides: Record<string, unknown> = {}) {
  return { total: 1, pending: 1, in_flight: 0, completed: 0, failed: 0, stalled: 0, ...overrides };
}

function showQueue(entries: unknown[], stats = makeStats()) {
  server.use(
    http.get('/api/v2/downloads', () => HttpResponse.json({ entries, stats })),
  );
}

/** The controls for one entry, so a page-wide "Remove" is never ambiguous. */
function entryRow(title: string) {
  return within(screen.getByText(title).closest('.bg-white') as HTMLElement);
}

describe('DownloadQueuePage', () => {
  it('Process Queue starts the job and reports its progress', async () => {
    showQueue([makeEntry()]);
    const calls = recordRequests('post', '/api/v2/downloads/process', { job_id: 12 });
    server.use(
      http.get('/api/v2/jobs/12', () =>
        HttpResponse.json({ id: 12, status: 'running', progress: 2, total: 5 }),
      ),
    );

    renderWithProviders(<DownloadQueuePage />);
    await userEvent.click(await screen.findByRole('button', { name: /process queue/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(await screen.findByText(/processing downloads/i)).toBeInTheDocument();
  });

  it('reports a failed queue job instead of leaving it looking busy', async () => {
    showQueue([makeEntry()]);
    recordRequests('post', '/api/v2/downloads/process', { job_id: 12 });
    server.use(
      http.get('/api/v2/jobs/12', () =>
        HttpResponse.json({ id: 12, status: 'failed', error_message: 'no worker' }),
      ),
    );

    renderWithProviders(<DownloadQueuePage />);
    await userEvent.click(await screen.findByRole('button', { name: /process queue/i }));

    expect(await screen.findByText(/no worker/i)).toBeInTheDocument();
  });

  it('Retry posts to that entry, and only shows for failed entries', async () => {
    showQueue([makeEntry({ id: 11, status: 'failed' })]);
    const calls = recordRequests('post', '/api/v2/downloads/11/retry');

    renderWithProviders(<DownloadQueuePage />);
    await userEvent.click(await screen.findByRole('button', { name: /retry/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
  });

  it('offers Retry on a stalled entry even though its status is not failed', async () => {
    // A stalled entry is the one case where the user most needs the button,
    // and its status still reads "downloading".
    showQueue([makeEntry({ status: 'downloading', stalled: true })]);
    renderWithProviders(<DownloadQueuePage />);

    expect(await screen.findByRole('button', { name: /retry/i })).toBeInTheDocument();
  });

  it('does not offer Retry on a pending entry', async () => {
    showQueue([makeEntry({ status: 'pending' })]);
    renderWithProviders(<DownloadQueuePage />);

    await screen.findByText('The Hobbit');
    expect(screen.queryByRole('button', { name: /retry/i })).toBeNull();
  });

  it('Read patches the entry as read', async () => {
    showQueue([makeEntry({ id: 11, read: false })]);
    const calls = recordRequests('patch', '/api/v2/downloads/11');

    renderWithProviders(<DownloadQueuePage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Read' }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toEqual({ read: true });
  });

  it('Unread patches it back', async () => {
    showQueue([makeEntry({ id: 11, read: true })]);
    const calls = recordRequests('patch', '/api/v2/downloads/11');

    renderWithProviders(<DownloadQueuePage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Unread' }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toEqual({ read: false });
  });

  it('Remove deletes that entry after confirmation', async () => {
    showQueue([makeEntry({ id: 11 })]);
    stubConfirm(true);
    const calls = recordRequests('delete', '/api/v2/downloads/11');

    renderWithProviders(<DownloadQueuePage />);
    await screen.findByText('The Hobbit');
    await userEvent.click(entryRow('The Hobbit').getByRole('button', { name: 'Remove' }));

    await waitFor(() => expect(calls).toHaveLength(1));
  });

  it('does not remove when the confirmation is dismissed', async () => {
    showQueue([makeEntry({ id: 11 })]);
    stubConfirm(false);
    const calls = recordRequests('delete', '/api/v2/downloads/11');

    renderWithProviders(<DownloadQueuePage />);
    await screen.findByText('The Hobbit');
    await userEvent.click(entryRow('The Hobbit').getByRole('button', { name: 'Remove' }));

    expect(calls).toHaveLength(0);
  });

  it('Re-queue stuck only appears when something is stalled, and posts reap-stale', async () => {
    showQueue([makeEntry({ stalled: true })], makeStats({ stalled: 1 }));
    const calls = recordRequests('post', '/api/v2/downloads/reap-stale', {
      checked: 1, requeued: 1, failed: 0,
    });

    renderWithProviders(<DownloadQueuePage />);
    await userEvent.click(await screen.findByRole('button', { name: /re-queue stuck/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
  });

  it('hides the stalled banner when nothing is stuck', async () => {
    showQueue([makeEntry()], makeStats({ stalled: 0 }));
    renderWithProviders(<DownloadQueuePage />);

    await screen.findByText('The Hobbit');
    expect(screen.queryByRole('button', { name: /re-queue stuck/i })).toBeNull();
  });

  describe('bulk actions', () => {
    async function selectFirstEntry() {
      const checkboxes = await screen.findAllByRole('checkbox');
      await userEvent.click(checkboxes[1]);
    }

    it('Mark Read sends the selected ids', async () => {
      showQueue([makeEntry({ id: 11 }), makeEntry({ id: 12, book_title: 'Dune' })]);
      const calls = recordRequests('post', '/api/v2/downloads/bulk');

      renderWithProviders(<DownloadQueuePage />);
      await selectFirstEntry();
      await userEvent.click(screen.getByRole('button', { name: /mark read/i }));

      await waitFor(() => expect(calls).toHaveLength(1));
      expect(calls[0].body).toEqual({ action: 'mark_read', entry_ids: [11] });
    });

    it('Mark Unread sends the mark_unread action', async () => {
      showQueue([makeEntry({ id: 11 })]);
      const calls = recordRequests('post', '/api/v2/downloads/bulk');

      renderWithProviders(<DownloadQueuePage />);
      await selectFirstEntry();
      await userEvent.click(screen.getByRole('button', { name: /mark unread/i }));

      await waitFor(() => expect(calls).toHaveLength(1));
      expect(calls[0].body.action).toBe('mark_unread');
    });

    it('Re-queue sends the retry action', async () => {
      showQueue([makeEntry({ id: 11 })]);
      const calls = recordRequests('post', '/api/v2/downloads/bulk');

      renderWithProviders(<DownloadQueuePage />);
      await selectFirstEntry();
      await userEvent.click(screen.getByRole('button', { name: /^re-queue$/i }));

      await waitFor(() => expect(calls).toHaveLength(1));
      expect(calls[0].body.action).toBe('retry');
    });

    it('bulk Remove confirms and sends every selected id', async () => {
      showQueue([makeEntry({ id: 11 }), makeEntry({ id: 12, book_title: 'Dune' })]);
      stubConfirm(true);
      const calls = recordRequests('post', '/api/v2/downloads/bulk');

      renderWithProviders(<DownloadQueuePage />);
      await userEvent.click((await screen.findAllByRole('checkbox'))[0]); // select all
      await userEvent.click(screen.getAllByRole('button', { name: 'Remove' })[0]);

      await waitFor(() => expect(calls).toHaveLength(1));
      expect(calls[0].body).toEqual({ action: 'remove', entry_ids: [11, 12] });
    });

    it('does not bulk remove when the confirmation is dismissed', async () => {
      showQueue([makeEntry({ id: 11 })]);
      stubConfirm(false);
      const calls = recordRequests('post', '/api/v2/downloads/bulk');

      renderWithProviders(<DownloadQueuePage />);
      await selectFirstEntry();
      await userEvent.click(screen.getAllByRole('button', { name: 'Remove' })[0]);

      expect(calls).toHaveLength(0);
    });

    it('clears the selection after a bulk action, so the next one cannot reuse it', async () => {
      showQueue([makeEntry({ id: 11 })]);
      const calls = recordRequests('post', '/api/v2/downloads/bulk');

      renderWithProviders(<DownloadQueuePage />);
      await selectFirstEntry();
      await userEvent.click(screen.getByRole('button', { name: /mark read/i }));

      await waitFor(() => expect(calls).toHaveLength(1));
      await waitFor(() => expect(screen.queryByText(/1 selected/)).toBeNull());
    });

    it('hides the bulk bar until something is selected', async () => {
      showQueue([makeEntry()]);
      renderWithProviders(<DownloadQueuePage />);

      await screen.findByText('The Hobbit');
      expect(screen.queryByRole('button', { name: /mark read/i })).toBeNull();
    });
  });

  describe('filters', () => {
    it('sends the search term', async () => {
      const calls = recordRequests('get', '/api/v2/downloads', {
        entries: [], stats: makeStats(),
      });

      renderWithProviders(<DownloadQueuePage />);
      await userEvent.type(await screen.findByPlaceholderText(/search/i), 'hobbit');

      await waitFor(() =>
        expect(lastRequest(calls).url.searchParams.get('search')).toBe('hobbit'),
      );
    });

    it('defaults to unread, so completed noise does not bury the live queue', async () => {
      const calls = recordRequests('get', '/api/v2/downloads', {
        entries: [], stats: makeStats(),
      });

      renderWithProviders(<DownloadQueuePage />);

      await waitFor(() => expect(calls.length).toBeGreaterThan(0));
      expect(calls[0].url.searchParams.get('read_status')).toBe('unread');
    });

    it('sends the chosen status filter', async () => {
      const calls = recordRequests('get', '/api/v2/downloads', {
        entries: [], stats: makeStats(),
      });

      renderWithProviders(<DownloadQueuePage />);
      const [statusSelect] = await screen.findAllByRole('combobox');
      await userEvent.selectOptions(statusSelect, 'failed');

      await waitFor(() =>
        expect(lastRequest(calls).url.searchParams.get('status')).toBe('failed'),
      );
    });

    it('flips the sort order', async () => {
      const calls = recordRequests('get', '/api/v2/downloads', {
        entries: [], stats: makeStats(),
      });

      renderWithProviders(<DownloadQueuePage />);
      await userEvent.click(await screen.findByRole('button', { name: /newest first/i }));

      await waitFor(() =>
        expect(lastRequest(calls).url.searchParams.get('order')).toBe('asc'),
      );
    });
  });
});
