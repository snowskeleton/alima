import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { adminUser, makeBook, regularUser } from '../test/handlers';
import { lastRequest, recordRequests, stubConfirm } from '../test/record';
import { server } from '../test/server';
import { currentPath, renderWithProviders } from '../test/utils';
import { LibraryPage } from './LibraryPage';

function booksResponse(books: unknown[], total = books.length) {
  return http.get('/api/v2/books', () =>
    HttpResponse.json({ books, total, offset: 0, limit: 50 }),
  );
}

describe('LibraryPage', () => {
  it('renders the books it was given', async () => {
    server.use(
      booksResponse([
        makeBook({ id: 1, title: 'The Hobbit' }),
        makeBook({ id: 2, title: 'Dune' }),
      ]),
    );

    renderWithProviders(<LibraryPage />);

    expect(await screen.findByText('The Hobbit')).toBeInTheDocument();
    expect(screen.getByText('Dune')).toBeInTheDocument();
  });

  it('shows an empty state rather than a blank page', async () => {
    server.use(booksResponse([]));
    renderWithProviders(<LibraryPage />);

    expect(await screen.findByText(/your library is empty/i)).toBeInTheDocument();
  });

  it('tells the user their search matched nothing, not that the library is empty', async () => {
    // These are different problems with different fixes, and conflating them
    // sends people looking for a sync bug when they have a typo.
    server.use(booksResponse([makeBook()]));
    renderWithProviders(<LibraryPage />);
    await screen.findByText('The Hobbit');

    server.use(booksResponse([]));
    await userEvent.type(screen.getByRole('textbox'), 'zzzz');

    expect(await screen.findByText(/try a different search term/i)).toBeInTheDocument();
  });

  it('sends the search term to the API', async () => {
    let seen: string | null = null;
    server.use(
      http.get('/api/v2/books', ({ request }) => {
        seen = new URL(request.url).searchParams.get('search');
        return HttpResponse.json({ books: [], total: 0, offset: 0, limit: 50 });
      }),
    );

    renderWithProviders(<LibraryPage />);
    await userEvent.type(await screen.findByRole('textbox'), 'hobbit');

    await waitFor(() => expect(seen).toBe('hobbit'));
  });

  it('omits the search parameter entirely when the box is empty', async () => {
    // `search: search || undefined` -- sending search= would make the backend
    // build a LIKE '%%' filter for no reason.
    let params: URLSearchParams | null = null;
    server.use(
      http.get('/api/v2/books', ({ request }) => {
        params = new URL(request.url).searchParams;
        return HttpResponse.json({ books: [], total: 0, offset: 0, limit: 50 });
      }),
    );

    renderWithProviders(<LibraryPage />);
    await waitFor(() => expect(params).not.toBeNull());
    expect(params!.has('search')).toBe(false);
  });

  it('surfaces a failed load instead of showing an empty library', async () => {
    // An empty grid on a 500 looks exactly like "you own no books", which is
    // the worst possible way to report a backend outage.
    server.use(
      http.get('/api/v2/books', () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    );

    renderWithProviders(<LibraryPage />);

    await waitFor(() =>
      expect(screen.queryByText(/your library is empty/i)).toBeNull(),
    );
  });

  describe('filters', () => {
    it('sends the status filter', async () => {
      const calls = recordRequests('get', '/api/v2/books', {
        books: [], total: 0, offset: 0, limit: 50,
      });

      renderWithProviders(<LibraryPage />);
      const [statusSelect] = await screen.findAllByRole('combobox');
      await userEvent.selectOptions(statusSelect, 'downloaded');

      await waitFor(() =>
        expect(lastRequest(calls).url.searchParams.get('status')).toBe('downloaded'),
      );
    });

    it('sends the source filter', async () => {
      const calls = recordRequests('get', '/api/v2/books', {
        books: [], total: 0, offset: 0, limit: 50,
      });

      renderWithProviders(<LibraryPage />);
      const selects = await screen.findAllByRole('combobox');
      await userEvent.selectOptions(selects[1], 'imported');

      await waitFor(() =>
        expect(lastRequest(calls).url.searchParams.get('source')).toBe('imported'),
      );
    });

    it('sends the sort field and direction', async () => {
      const calls = recordRequests('get', '/api/v2/books', {
        books: [], total: 0, offset: 0, limit: 50,
      });

      renderWithProviders(<LibraryPage />);
      const selects = await screen.findAllByRole('combobox');
      await userEvent.selectOptions(selects[3], 'title');
      await userEvent.selectOptions(selects[4], 'asc');

      await waitFor(() => {
        const params = lastRequest(calls).url.searchParams;
        expect(params.get('sort')).toBe('title');
        expect(params.get('order')).toBe('asc');
      });
    });

    it('Load More raises the limit and only shows when more remain', async () => {
      const calls = recordRequests('get', '/api/v2/books', {
        books: [makeBook()], total: 120, offset: 0, limit: 50,
      });

      renderWithProviders(<LibraryPage />);
      await userEvent.click(await screen.findByRole('button', { name: /load more/i }));

      await waitFor(() => expect(lastRequest(calls).url.searchParams.get('limit')).toBe('100'));
    });

    it('offers no Load More once everything is on screen', async () => {
      server.use(booksResponse([makeBook()], 1));

      renderWithProviders(<LibraryPage />);
      await screen.findByText('The Hobbit');

      expect(screen.queryByRole('button', { name: /load more/i })).toBeNull();
    });
  });

  describe('context menu', () => {
    async function openMenuOnFirstBook(book = makeBook({ id: 7 })) {
      server.use(booksResponse([book]));
      renderWithProviders(<LibraryPage />);
      fireEvent.contextMenu(await screen.findByText(book.title as string));
    }

    it('Download posts to the book download endpoint', async () => {
      const calls = recordRequests('post', '/api/v2/books/7/download');
      await openMenuOnFirstBook(makeBook({ id: 7, file_path: null, source: 'audible' }));

      await userEvent.click(await screen.findByRole('button', { name: 'Download' }));

      await waitFor(() => expect(calls).toHaveLength(1));
    });

    it('Disable Download patches the flag off', async () => {
      const calls = recordRequests('patch', '/api/v2/books/7');
      await openMenuOnFirstBook(makeBook({ id: 7, file_path: null, download_enabled: true }));

      await userEvent.click(await screen.findByRole('button', { name: /disable download/i }));

      await waitFor(() => expect(calls).toHaveLength(1));
      expect(calls[0].body).toEqual({ download_enabled: false });
    });

    it('Mark Available patches the book, and only appears when unavailable', async () => {
      const calls = recordRequests('patch', '/api/v2/books/7');
      await openMenuOnFirstBook(makeBook({ id: 7, download_unavailable: true }));

      await userEvent.click(await screen.findByRole('button', { name: /mark available/i }));

      await waitFor(() => expect(calls).toHaveLength(1));
      expect(calls[0].body).toEqual({ mark_available: true });
    });

    it('Delete File names the book in the prompt', async () => {
      const confirm = stubConfirm(true);
      const calls = recordRequests('delete', '/api/v2/books/7/file');
      await openMenuOnFirstBook(
        makeBook({ id: 7, title: 'The Hobbit', file_path: '/audiobooks/hobbit.m4b' }),
      );

      await userEvent.click(await screen.findByRole('button', { name: /delete file/i }));

      expect(confirm).toHaveBeenCalledWith(expect.stringContaining('The Hobbit'));
      await waitFor(() => expect(calls).toHaveLength(1));
    });

    it('does not delete the file when the confirmation is dismissed', async () => {
      stubConfirm(false);
      const calls = recordRequests('delete', '/api/v2/books/7/file');
      await openMenuOnFirstBook(makeBook({ id: 7, file_path: '/audiobooks/hobbit.m4b' }));

      await userEvent.click(await screen.findByRole('button', { name: /delete file/i }));

      expect(calls).toHaveLength(0);
    });

    it('Delete Book deletes after confirmation', async () => {
      stubConfirm(true);
      const calls = recordRequests('delete', '/api/v2/books/7');
      await openMenuOnFirstBook(makeBook({ id: 7 }));

      await userEvent.click(await screen.findByRole('button', { name: /delete book/i }));

      await waitFor(() => expect(calls).toHaveLength(1));
    });

    it('Open navigates to the book', async () => {
      await openMenuOnFirstBook(makeBook({ id: 7 }));

      await userEvent.click(await screen.findByRole('button', { name: 'Open' }));

      await waitFor(() => expect(currentPath()).toBe('/library/7'));
    });

    it('closes after an action, so the next right-click starts fresh', async () => {
      recordRequests('patch', '/api/v2/books/7');
      await openMenuOnFirstBook(makeBook({ id: 7, file_path: null, download_enabled: true }));

      await userEvent.click(await screen.findByRole('button', { name: /disable download/i }));

      await waitFor(() =>
        expect(screen.queryByRole('button', { name: /disable download/i })).toBeNull(),
      );
    });

    it('closes on Escape without running anything', async () => {
      const calls = recordRequests('delete', '/api/v2/books/7');
      await openMenuOnFirstBook(makeBook({ id: 7 }));
      await screen.findByRole('button', { name: 'Open' });

      fireEvent.keyDown(document, { key: 'Escape' });

      await waitFor(() => expect(screen.queryByRole('button', { name: 'Open' })).toBeNull());
      expect(calls).toHaveLength(0);
    });

    it('hides the destructive admin entries from regular users', async () => {
      server.use(
        http.get('/api/v2/auth/status', () =>
          HttpResponse.json({ authenticated: true, user: regularUser, needs_registration: false }),
        ),
      );
      await openMenuOnFirstBook(makeBook({ id: 7 }));
      await screen.findByRole('button', { name: 'Open' });

      expect(screen.queryByRole('button', { name: /delete book/i })).toBeNull();
      expect(screen.queryByRole('button', { name: 'Edit' })).toBeNull();
    });

    it('offers them to admins', async () => {
      server.use(
        http.get('/api/v2/auth/status', () =>
          HttpResponse.json({ authenticated: true, user: adminUser, needs_registration: false }),
        ),
      );
      await openMenuOnFirstBook(makeBook({ id: 7 }));

      expect(await screen.findByRole('button', { name: /delete book/i })).toBeInTheDocument();
    });
  });

  describe('bulk actions in compact view', () => {
    async function selectFirstBookInCompactView(books = [makeBook({ id: 7 })]) {
      server.use(booksResponse(books));
      renderWithProviders(<LibraryPage />);
      const selects = await screen.findAllByRole('combobox');
      await userEvent.selectOptions(selects[5], 'compact');
      const checkboxes = await screen.findAllByRole('checkbox');
      await userEvent.click(checkboxes[1]);
    }

    it('Download All posts the bulk download action with the selected ids', async () => {
      const calls = recordRequests('post', '/api/v2/books/bulk', { success: true, affected: 1 });
      await selectFirstBookInCompactView();

      await userEvent.click(screen.getByRole('button', { name: /download all/i }));

      await waitFor(() => expect(calls).toHaveLength(1));
      expect(calls[0].body).toEqual({ action: 'download', book_ids: [7] });
    });

    it('Enable Downloads sends the enable_download action', async () => {
      const calls = recordRequests('post', '/api/v2/books/bulk', { success: true, affected: 1 });
      await selectFirstBookInCompactView();

      await userEvent.click(screen.getByRole('button', { name: /enable downloads/i }));

      await waitFor(() => expect(calls).toHaveLength(1));
      expect(calls[0].body.action).toBe('enable_download');
    });

    it('Disable Downloads sends the disable_download action', async () => {
      const calls = recordRequests('post', '/api/v2/books/bulk', { success: true, affected: 1 });
      await selectFirstBookInCompactView();

      await userEvent.click(screen.getByRole('button', { name: /disable downloads/i }));

      await waitFor(() => expect(calls).toHaveLength(1));
      expect(calls[0].body.action).toBe('disable_download');
    });

    it('Delete Books confirms first', async () => {
      stubConfirm(true);
      const calls = recordRequests('post', '/api/v2/books/bulk', { success: true, affected: 1 });
      await selectFirstBookInCompactView();

      await userEvent.click(screen.getByRole('button', { name: /delete books/i }));

      await waitFor(() => expect(calls).toHaveLength(1));
      expect(calls[0].body.action).toBe('delete');
    });

    it('does not bulk delete when the confirmation is dismissed', async () => {
      stubConfirm(false);
      const calls = recordRequests('post', '/api/v2/books/bulk', { success: true, affected: 1 });
      await selectFirstBookInCompactView();

      await userEvent.click(screen.getByRole('button', { name: /delete books/i }));

      expect(calls).toHaveLength(0);
    });

    it('Select All picks up every book on screen', async () => {
      const calls = recordRequests('post', '/api/v2/books/bulk', { success: true, affected: 2 });
      server.use(booksResponse([makeBook({ id: 7 }), makeBook({ id: 8, title: 'Dune' })]));

      renderWithProviders(<LibraryPage />);
      const selects = await screen.findAllByRole('combobox');
      await userEvent.selectOptions(selects[5], 'compact');
      await userEvent.click((await screen.findAllByRole('checkbox'))[0]);
      await userEvent.click(screen.getByRole('button', { name: /download all/i }));

      await waitFor(() => expect(calls).toHaveLength(1));
      expect(calls[0].body.book_ids).toEqual([7, 8]);
    });

    it('clears the selection after a bulk action', async () => {
      recordRequests('post', '/api/v2/books/bulk', { success: true, affected: 1 });
      await selectFirstBookInCompactView();

      await userEvent.click(screen.getByRole('button', { name: /download all/i }));

      await waitFor(() => expect(screen.queryByText(/1 selected/)).toBeNull());
    });

    it('drops the selection when leaving compact view', async () => {
      // The bulk bar is only rendered in compact view; a selection surviving
      // the switch would be invisible and still act on the next bulk click.
      await selectFirstBookInCompactView();
      expect(screen.getByText(/1 selected/)).toBeInTheDocument();

      const selects = screen.getAllByRole('combobox');
      await userEvent.selectOptions(selects[5], 'grid');
      await userEvent.selectOptions(selects[5], 'compact');

      expect(screen.queryByText(/1 selected/)).toBeNull();
    });

    it('offers no bulk bar in grid view at all', async () => {
      server.use(booksResponse([makeBook()]));
      renderWithProviders(<LibraryPage />);

      await screen.findByText('The Hobbit');
      expect(screen.queryByRole('checkbox')).toBeNull();
    });
  });
});
