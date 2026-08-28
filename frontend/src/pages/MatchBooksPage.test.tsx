import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { recordRequests, stubConfirm } from '../test/record';
import { server } from '../test/server';
import { renderWithProviders } from '../test/utils';
import { MatchBooksPage } from './MatchBooksPage';

function makeMatch(overrides: Record<string, unknown> = {}) {
  return {
    filename: 'hobbit.m4b',
    file_path: '/unassigned/hobbit.m4b',
    candidates: [
      { book_id: 1, title: 'The Hobbit', author: 'J.R.R. Tolkien', score: 0.95 },
      { book_id: 2, title: 'The Habit', author: 'Someone Else', score: 0.4 },
    ],
    ...overrides,
  };
}

function showMatches(...matches: unknown[]) {
  server.use(
    http.get('/api/v2/match-books/matches', () => HttpResponse.json({ matches })),
  );
}

/** The row for one candidate, so "Confirm" is unambiguous. */
function candidateRow(title: string) {
  return within(screen.getByText(title).closest('.justify-between') as HTMLElement);
}

describe('MatchBooksPage', () => {
  it('Confirm posts the filename and the chosen book', async () => {
    showMatches(makeMatch());
    const calls = recordRequests('post', '/api/v2/match-books/confirm');

    renderWithProviders(<MatchBooksPage />);
    await screen.findByText('The Hobbit');
    await userEvent.click(candidateRow('The Hobbit').getByRole('button', { name: /confirm/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toEqual({ filename: 'hobbit.m4b', book_id: 1 });
    expect(await screen.findByText(/match confirmed/i)).toBeInTheDocument();
  });

  it('confirms the candidate whose row was clicked, not the top-scoring one', async () => {
    showMatches(makeMatch());
    const calls = recordRequests('post', '/api/v2/match-books/confirm');

    renderWithProviders(<MatchBooksPage />);
    await screen.findByText('The Habit');
    await userEvent.click(candidateRow('The Habit').getByRole('button', { name: /confirm/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body.book_id).toBe(2);
  });

  it('Import as New posts the filename', async () => {
    showMatches(makeMatch());
    const calls = recordRequests('post', '/api/v2/match-books/import');

    renderWithProviders(<MatchBooksPage />);
    await userEvent.click(await screen.findByRole('button', { name: /import as new/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toEqual({ filename: 'hobbit.m4b' });
  });

  it('Delete names the file and deletes it on confirm', async () => {
    showMatches(makeMatch({ filename: 'hobbit.m4b' }));
    const confirm = stubConfirm(true);
    const calls = recordRequests('delete', '/api/v2/match-books/:filename');

    renderWithProviders(<MatchBooksPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Delete' }));

    expect(confirm).toHaveBeenCalledWith(expect.stringContaining('hobbit.m4b'));
    await waitFor(() => expect(calls).toHaveLength(1));
  });

  it('escapes the filename in the delete URL', async () => {
    // Unencoded slashes and spaces would either 404 or address a different
    // file than the one the user clicked.
    showMatches(makeMatch({ filename: 'the hobbit & friends.m4b' }));
    stubConfirm(true);
    const calls = recordRequests('delete', '/api/v2/match-books/:filename');

    renderWithProviders(<MatchBooksPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Delete' }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].url.pathname).toBe(
      `/api/v2/match-books/${encodeURIComponent('the hobbit & friends.m4b')}`,
    );
  });

  it('does not delete when the confirmation is dismissed', async () => {
    showMatches(makeMatch());
    stubConfirm(false);
    const calls = recordRequests('delete', '/api/v2/match-books/:filename');

    renderWithProviders(<MatchBooksPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Delete' }));

    expect(calls).toHaveLength(0);
  });

  it('batch-confirms every radio selection in one request', async () => {
    showMatches(
      makeMatch({ filename: 'hobbit.m4b' }),
      makeMatch({
        filename: 'dune.m4b',
        candidates: [{ book_id: 5, title: 'Dune', author: 'Frank Herbert', score: 0.9 }],
      }),
    );
    const calls = recordRequests('post', '/api/v2/match-books/batch-confirm', {
      confirmed: 2, total: 2,
    });

    renderWithProviders(<MatchBooksPage />);
    const radios = await screen.findAllByRole('radio');
    await userEvent.click(radios[0]);
    await userEvent.click(radios[2]);
    await userEvent.click(screen.getByRole('button', { name: /confirm 2 selected/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toEqual({
      matches: [
        { filename: 'hobbit.m4b', book_id: 1 },
        { filename: 'dune.m4b', book_id: 5 },
      ],
    });
    expect(await screen.findByText(/confirmed 2\/2/i)).toBeInTheDocument();
  });

  it('replaces the selection for a file rather than queuing two matches for it', async () => {
    // The radios share a name per file, so picking again must overwrite; two
    // entries for one filename would match the file twice.
    showMatches(makeMatch());
    const calls = recordRequests('post', '/api/v2/match-books/batch-confirm', {
      confirmed: 1, total: 1,
    });

    renderWithProviders(<MatchBooksPage />);
    const radios = await screen.findAllByRole('radio');
    await userEvent.click(radios[0]);
    await userEvent.click(radios[1]);
    await userEvent.click(screen.getByRole('button', { name: /confirm 1 selected/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body.matches).toEqual([{ filename: 'hobbit.m4b', book_id: 2 }]);
  });

  it('hides the batch button until something is selected', async () => {
    showMatches(makeMatch());
    renderWithProviders(<MatchBooksPage />);

    await screen.findByText('hobbit.m4b');
    expect(screen.queryByRole('button', { name: /selected/i })).toBeNull();
  });

  it('says so when a file has no candidates at all', async () => {
    showMatches(makeMatch({ candidates: [] }));
    renderWithProviders(<MatchBooksPage />);

    expect(await screen.findByText(/no matching candidates/i)).toBeInTheDocument();
  });

  it('shows an empty state when everything is matched', async () => {
    showMatches();
    renderWithProviders(<MatchBooksPage />);

    expect(await screen.findByText(/no unmatched files/i)).toBeInTheDocument();
  });
});
