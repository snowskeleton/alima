import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { makeBook } from '../test/handlers';
import { recordRequests, stubConfirm } from '../test/record';
import { server } from '../test/server';
import { currentPath, renderWithProviders } from '../test/utils';
import { BookEditPage } from './BookEditPage';

function showBook(overrides: Record<string, unknown> = {}) {
  server.use(http.get('/api/v2/books/:id', () => HttpResponse.json(makeBook(overrides))));
}

function render() {
  return renderWithProviders(<BookEditPage />, {
    route: '/books/7/edit',
    path: '/books/:bookId/edit',
  });
}

describe('BookEditPage', () => {
  it('prefills the form from the book it loaded', async () => {
    showBook({ id: 7, title: 'The Hobbit', author: 'J.R.R. Tolkien' });
    render();

    expect(await screen.findByLabelText(/^title$/i)).toHaveValue('The Hobbit');
    expect(screen.getByLabelText(/^author$/i)).toHaveValue('J.R.R. Tolkien');
  });

  it('prefers an existing override over the upstream value', async () => {
    // Otherwise opening the editor and saving would silently discard the
    // override the user made last time.
    showBook({
      id: 7,
      title: 'The Hobbit',
      metadata_override: { title: 'The Hobbit (Unabridged)' },
    });
    render();

    expect(await screen.findByLabelText(/^title$/i)).toHaveValue('The Hobbit (Unabridged)');
  });

  it('PUTs the edited metadata to this book', async () => {
    showBook({ id: 7, title: 'The Hobbit' });
    const calls = recordRequests('put', '/api/v2/books/7/metadata');

    render();
    const title = await screen.findByLabelText(/^title$/i);
    await userEvent.clear(title);
    await userEvent.type(title, 'There and Back Again');
    await userEvent.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body.title).toBe('There and Back Again');
    await waitFor(() => expect(currentPath()).toBe('/library/7'));
  });

  it('stays on the form when the save fails', async () => {
    // Navigating away on a failed save loses the user's edits and tells them
    // it worked.
    showBook({ id: 7 });
    recordRequests('put', '/api/v2/books/7/metadata', { detail: 'boom' }, { status: 500 });

    render();
    await userEvent.click(await screen.findByRole('button', { name: /save changes/i }));

    await waitFor(() => expect(currentPath()).toBe('/books/7/edit'));
  });

  it('sends every editable field, not just the changed one', async () => {
    // The endpoint replaces the override wholesale, so a partial body would
    // wipe the fields the user did not touch this time.
    showBook({ id: 7, author: 'J.R.R. Tolkien', narrator: 'Rob Inglis' });
    const calls = recordRequests('put', '/api/v2/books/7/metadata');

    render();
    await userEvent.click(await screen.findByRole('button', { name: /save changes/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toMatchObject({
      author: 'J.R.R. Tolkien',
      narrator: 'Rob Inglis',
    });
    expect(Object.keys(calls[0].body).sort()).toEqual([
      'author', 'description', 'narrator', 'publisher',
      'series', 'series_position', 'subtitle', 'title',
    ]);
  });

  it('Reset to Original deletes the override after confirmation', async () => {
    showBook({ id: 7 });
    stubConfirm(true);
    const calls = recordRequests('delete', '/api/v2/books/7/metadata');

    render();
    await userEvent.click(await screen.findByRole('button', { name: /reset to original/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
  });

  it('does not reset when the confirmation is dismissed', async () => {
    showBook({ id: 7 });
    stubConfirm(false);
    const calls = recordRequests('delete', '/api/v2/books/7/metadata');

    render();
    await userEvent.click(await screen.findByRole('button', { name: /reset to original/i }));

    expect(calls).toHaveLength(0);
  });

  it('reports a missing book instead of an empty form', async () => {
    server.use(
      http.get('/api/v2/books/:id', () =>
        HttpResponse.json({ detail: 'Not found' }, { status: 404 }),
      ),
    );
    render();

    expect(await screen.findByText(/book not found/i)).toBeInTheDocument();
  });
});
