import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { makeBook } from '../test/handlers';
import { server } from '../test/server';
import { renderWithProviders } from '../test/utils';
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
});
