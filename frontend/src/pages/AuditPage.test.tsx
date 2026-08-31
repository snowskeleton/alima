import { act, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { recordRequests, stubConfirm, stubEventSource } from '../test/record';
import { server } from '../test/server';
import { renderWithProviders } from '../test/utils';
import { AuditPage } from './AuditPage';

function makeResult(overrides: Record<string, unknown> = {}) {
  return {
    status: 'bad',
    book_title: 'The Hobbit',
    book_author: 'J.R.R. Tolkien',
    file_title: 'Dune',
    file_author: 'Frank Herbert',
    title_score: 0.2,
    author_score: 0.1,
    file_path: '/audiobooks/dune.m4b',
    ...overrides,
  };
}

function showAudit(
  status: { last_run_id: number | null; running_run_id: number | null },
  results: unknown[] = [],
  summary: unknown = null,
) {
  server.use(
    http.get('/api/v2/audit', () => HttpResponse.json(status)),
    http.get('/api/v2/audit/results/:id', () =>
      HttpResponse.json({
        results,
        summary: summary ?? {
          total_scanned: results.length, mismatches: 0, missing_files: 0,
          good: results.length, status: 'completed',
        },
      }),
    ),
  );
}

describe('AuditPage', () => {
  it('Start Audit posts and then follows the new run', async () => {
    showAudit({ last_run_id: null, running_run_id: null });
    const sse = stubEventSource();
    const calls = recordRequests('post', '/api/v2/audit/start', {
      audit_id: 42, already_running: false,
    });

    renderWithProviders(<AuditPage />);
    await userEvent.click((await screen.findAllByRole('button', { name: /start audit/i }))[0]);

    await waitFor(() => expect(calls).toHaveLength(1));
    await waitFor(() => expect(sse.url).toContain('/api/v2/audit/stream/42'));
  });

  it('does not adopt the returned id when an audit was already running', async () => {
    // The backend answers with the in-flight run's id and already_running:true;
    // treating that as a fresh start would show a second audit that isn't real.
    showAudit({ last_run_id: 7, running_run_id: null });
    stubEventSource();
    recordRequests('post', '/api/v2/audit/start', { audit_id: 7, already_running: true });

    renderWithProviders(<AuditPage />);
    await userEvent.click((await screen.findAllByRole('button', { name: /start audit/i }))[0]);

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /start audit/i })).toBeEnabled(),
    );
  });

  it('shows live progress from the event stream', async () => {
    showAudit({ last_run_id: null, running_run_id: 42 });
    const sse = stubEventSource();

    renderWithProviders(<AuditPage />);
    await waitFor(() => expect(sse.url).toContain('42'));
    act(() => sse.emit('audit_progress', { scanned: 3, total: 10, current_book: 'Dune' }));

    expect(await screen.findByText(/3\/10/)).toBeInTheDocument();
    expect(screen.getByText(/Dune/)).toBeInTheDocument();
  });

  it('disables Start while an audit is already running', async () => {
    showAudit({ last_run_id: null, running_run_id: 42 });
    stubEventSource();

    renderWithProviders(<AuditPage />);

    expect(await screen.findByRole('button', { name: /running/i })).toBeDisabled();
  });

  it('Unmatch posts the file path after confirmation', async () => {
    showAudit({ last_run_id: 7, running_run_id: null }, [
      makeResult({ status: 'bad', file_path: '/audiobooks/dune.m4b' }),
    ]);
    stubEventSource();
    stubConfirm(true);
    const calls = recordRequests('post', '/api/v2/audit/unmatch');

    renderWithProviders(<AuditPage />);
    await userEvent.click(await screen.findByRole('button', { name: /unmatch/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toEqual({ file_path: '/audiobooks/dune.m4b' });
  });

  it('does not unmatch when the confirmation is dismissed', async () => {
    showAudit({ last_run_id: 7, running_run_id: null }, [makeResult({ status: 'bad' })]);
    stubEventSource();
    stubConfirm(false);
    const calls = recordRequests('post', '/api/v2/audit/unmatch');

    renderWithProviders(<AuditPage />);
    await userEvent.click(await screen.findByRole('button', { name: /unmatch/i }));

    expect(calls).toHaveLength(0);
  });

  it('offers no Unmatch on a result that matched correctly', async () => {
    showAudit({ last_run_id: 7, running_run_id: null }, [makeResult({ status: 'good' })]);
    stubEventSource();

    renderWithProviders(<AuditPage />);
    await screen.findByText('The Hobbit');
    expect(screen.queryByRole('button', { name: /unmatch/i })).toBeNull();
  });

  it('filters the results by status', async () => {
    showAudit({ last_run_id: 7, running_run_id: null }, [
      makeResult({ status: 'good', book_title: 'The Hobbit' }),
      makeResult({ status: 'bad', book_title: 'Dune' }),
    ]);
    stubEventSource();

    renderWithProviders(<AuditPage />);
    await userEvent.click(await screen.findByRole('button', { name: /^good/i }));

    expect(screen.getByText('The Hobbit')).toBeInTheDocument();
    expect(screen.queryByText('Dune')).toBeNull();
  });

  it('offers a first run when there is nothing to show', async () => {
    server.use(
      http.get('/api/v2/audit', () =>
        HttpResponse.json({ last_run_id: null, running_run_id: null }),
      ),
    );
    stubEventSource();

    renderWithProviders(<AuditPage />);

    expect(await screen.findByText(/no audit results/i)).toBeInTheDocument();
  });
});
