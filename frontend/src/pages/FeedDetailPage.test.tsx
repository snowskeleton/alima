import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it, vi } from 'vitest';
import { adminUser, makeBook, makeFeed, regularUser } from '../test/handlers';
import { server } from '../test/server';
import { renderWithProviders } from '../test/utils';
import { FeedDetailPage } from './FeedDetailPage';

function showFeed(overrides: Record<string, unknown> = {}) {
  server.use(
    http.get('/api/v2/feeds/by-slug/:slug', () => HttpResponse.json(makeFeed(overrides))),
  );
}

function render(user: unknown = regularUser) {
  return renderWithProviders(<FeedDetailPage />, {
    route: '/feed/my-library',
    path: '/feed/:slug',
    auth: { authenticated: true, user, needs_registration: false },
  });
}

describe('FeedDetailPage', () => {
  it('lists the feed s episodes', async () => {
    showFeed({ books: [makeBook({ id: 1, title: 'The Hobbit' })] });
    render();

    expect(await screen.findByText('The Hobbit')).toBeInTheDocument();
  });

  it('filters episodes by title as the user types', async () => {
    showFeed({
      books: [
        makeBook({ id: 1, title: 'The Hobbit' }),
        makeBook({ id: 2, title: 'Dune' }),
      ],
    });
    render();

    await userEvent.type(await screen.findByPlaceholderText(/search by title/i), 'dune');

    expect(screen.getByText('Dune')).toBeInTheDocument();
    expect(screen.queryByText('The Hobbit')).toBeNull();
  });

  it('matches on narrator too, not only the title', async () => {
    showFeed({
      books: [
        makeBook({ id: 1, title: 'The Hobbit', narrator: 'Rob Inglis' }),
        makeBook({ id: 2, title: 'Dune', narrator: 'Simon Vance' }),
      ],
    });
    render();

    await userEvent.type(await screen.findByPlaceholderText(/search by title/i), 'vance');

    expect(screen.getByText('Dune')).toBeInTheDocument();
    expect(screen.queryByText('The Hobbit')).toBeNull();
  });

  it('says the search matched nothing rather than that the feed is empty', async () => {
    showFeed({ books: [makeBook({ id: 1, title: 'The Hobbit' })] });
    render();

    await userEvent.type(await screen.findByPlaceholderText(/search by title/i), 'zzz');

    expect(screen.getByText(/no episodes match/i)).toBeInTheDocument();
  });

  it('Clear restores the full list', async () => {
    showFeed({ books: [makeBook({ id: 1, title: 'The Hobbit' })] });
    render();

    await userEvent.type(await screen.findByPlaceholderText(/search by title/i), 'zzz');
    await userEvent.click(screen.getByRole('button', { name: /clear/i }));

    expect(await screen.findByText('The Hobbit')).toBeInTheDocument();
  });

  it('sorts by the chosen field and flips direction on demand', async () => {
    showFeed({
      books: [
        makeBook({ id: 1, title: 'Anna Karenina' }),
        makeBook({ id: 2, title: 'Zorba' }),
      ],
    });
    render();

    await userEvent.selectOptions(await screen.findByRole('combobox'), 'title');
    const descending = screen.getAllByText(/Anna Karenina|Zorba/).map((el) => el.textContent);
    expect(descending[0]).toBe('Zorba');

    await userEvent.click(screen.getByRole('button', { name: '↓' }));
    const ascending = screen.getAllByText(/Anna Karenina|Zorba/).map((el) => el.textContent);
    expect(ascending[0]).toBe('Anna Karenina');
  });

  it('copies the RSS URL and confirms it did', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    showFeed({ rss_url: 'https://example.com/feed/my-library.xml', books: [] });
    render();

    await userEvent.click(await screen.findByRole('button', { name: /^copy$/i }));

    expect(writeText).toHaveBeenCalledWith('https://example.com/feed/my-library.xml');
    expect(await screen.findByRole('button', { name: /copied!/i })).toBeInTheDocument();
  });

  it('offers Edit Feed to the feed s owner', async () => {
    showFeed({ user_id: regularUser.id, books: [] });
    render(regularUser);

    expect(await screen.findByRole('link', { name: /edit feed/i })).toBeInTheDocument();
  });

  it("does not offer Edit Feed on someone else's feed", async () => {
    showFeed({ user_id: 999, is_system: false, books: [] });
    render(regularUser);

    await screen.findByText('My Library');
    expect(screen.queryByRole('link', { name: /edit feed/i })).toBeNull();
  });

  it('lets an admin edit a system feed they do not own', async () => {
    showFeed({ user_id: 999, is_system: true, books: [] });
    render(adminUser);

    expect(await screen.findByRole('link', { name: /edit feed/i })).toBeInTheDocument();
  });

  it('reports a missing feed rather than an empty page', async () => {
    server.use(
      http.get('/api/v2/feeds/by-slug/:slug', () =>
        HttpResponse.json({ detail: 'Not found' }, { status: 404 }),
      ),
    );
    render();

    expect(await screen.findByText(/feed not found/i)).toBeInTheDocument();
  });
});
