import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { adminUser, makeBook, regularUser } from '../test/handlers';
import { recordRequests, stubConfirm } from '../test/record';
import { server } from '../test/server';
import { currentPath, renderWithProviders } from '../test/utils';
import { BookDetailPage } from './BookDetailPage';

function showBook(overrides: Record<string, unknown> = {}) {
  server.use(http.get('/api/v2/books/:id', () => HttpResponse.json(makeBook(overrides))));
}

function asUser(user: unknown) {
  server.use(
    http.get('/api/v2/auth/status', () =>
      HttpResponse.json({ authenticated: true, user, needs_registration: false }),
    ),
  );
}

function render() {
  return renderWithProviders(<BookDetailPage />, {
    route: '/books/1',
    path: '/books/:bookId',
  });
}

describe('BookDetailPage', () => {
  it('Download Now posts to the download endpoint for this book', async () => {
    showBook({ id: 7, file_path: null, source: 'audible' });
    const calls = recordRequests('post', '/api/v2/books/7/download');

    render();
    await userEvent.click(await screen.findByRole('button', { name: /download now/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
  });

  it('hides Download Now once the file is already on disk', async () => {
    showBook({ file_path: '/audiobooks/hobbit.m4b' });
    render();

    await screen.findByRole('button', { name: /unmatch file/i });
    expect(screen.queryByRole('button', { name: /download now/i })).toBeNull();
  });

  it('sends download_enabled: false when disabling auto-download', async () => {
    showBook({ id: 7, download_enabled: true });
    const calls = recordRequests('patch', '/api/v2/books/7');

    render();
    await userEvent.click(
      await screen.findByRole('button', { name: /disable auto-download/i }),
    );

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toEqual({ download_enabled: false });
  });

  it('sends download_enabled: true when the book is currently disabled', async () => {
    // The button label and the payload are derived from the same flag; getting
    // one inverted and not the other is the easy mistake here.
    showBook({ id: 7, download_enabled: false });
    const calls = recordRequests('patch', '/api/v2/books/7');

    render();
    await userEvent.click(
      await screen.findByRole('button', { name: /enable auto-download/i }),
    );

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toEqual({ download_enabled: true });
  });

  it('Mark Available patches mark_available and only shows when unavailable', async () => {
    showBook({ id: 7, download_unavailable: true });
    const calls = recordRequests('patch', '/api/v2/books/7');

    render();
    await userEvent.click(await screen.findByRole('button', { name: /mark available/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toEqual({ mark_available: true });
  });

  it('does not offer Mark Available for a book that is available', async () => {
    showBook({ download_unavailable: false });
    render();

    await screen.findByRole('button', { name: /auto-download/i });
    expect(screen.queryByRole('button', { name: /mark available/i })).toBeNull();
  });

  it('Unmatch File asks first and posts only on confirmation', async () => {
    showBook({ id: 7, file_path: '/audiobooks/hobbit.m4b' });
    const confirm = stubConfirm(true);
    const calls = recordRequests('post', '/api/v2/books/7/unmatch');

    render();
    await userEvent.click(await screen.findByRole('button', { name: /unmatch file/i }));

    expect(confirm).toHaveBeenCalled();
    await waitFor(() => expect(calls).toHaveLength(1));
  });

  it('does not unmatch when the confirmation is dismissed', async () => {
    showBook({ id: 7, file_path: '/audiobooks/hobbit.m4b' });
    stubConfirm(false);
    const calls = recordRequests('post', '/api/v2/books/7/unmatch');

    render();
    await userEvent.click(await screen.findByRole('button', { name: /unmatch file/i }));

    expect(calls).toHaveLength(0);
  });

  it('Delete File deletes the file, not the book', async () => {
    // /books/:id/file and /books/:id differ by one path segment and the wrong
    // one destroys the library row -- worth pinning explicitly.
    showBook({ id: 7, file_path: '/audiobooks/hobbit.m4b' });
    stubConfirm(true);
    const fileCalls = recordRequests('delete', '/api/v2/books/7/file');
    const bookCalls = recordRequests('delete', '/api/v2/books/7');

    render();
    await userEvent.click(await screen.findByRole('button', { name: /delete file/i }));

    await waitFor(() => expect(fileCalls).toHaveLength(1));
    expect(bookCalls).toHaveLength(0);
  });

  it('Delete Book deletes the book after confirmation', async () => {
    showBook({ id: 7 });
    stubConfirm(true);
    const calls = recordRequests('delete', '/api/v2/books/7');

    render();
    await userEvent.click(await screen.findByRole('button', { name: /delete book/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    await waitFor(() => expect(currentPath()).toBe('/library'));
  });

  it('does not delete the book when the confirmation is dismissed', async () => {
    showBook({ id: 7 });
    stubConfirm(false);
    const calls = recordRequests('delete', '/api/v2/books/7');

    render();
    await userEvent.click(await screen.findByRole('button', { name: /delete book/i }));

    expect(calls).toHaveLength(0);
  });

  it('offers Delete Book and Edit to admins only', async () => {
    asUser(adminUser);
    showBook();
    render();

    expect(await screen.findByRole('button', { name: /delete book/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /edit/i })).toBeInTheDocument();
  });

  it('hides the destructive admin controls from regular users', async () => {
    asUser(regularUser);
    showBook();
    render();

    await screen.findByRole('button', { name: /auto-download/i });
    expect(screen.queryByRole('button', { name: /delete book/i })).toBeNull();
    expect(screen.queryByRole('link', { name: /edit/i })).toBeNull();
  });

  it('reports a missing book rather than rendering an empty shell', async () => {
    server.use(
      http.get('/api/v2/books/:id', () =>
        HttpResponse.json({ detail: 'Not found' }, { status: 404 }),
      ),
    );
    render();

    expect(await screen.findByText(/book not found/i)).toBeInTheDocument();
  });
});
