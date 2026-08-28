import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it, vi } from 'vitest';
import { adminUser, makeFeed, regularUser } from '../test/handlers';
import { recordRequests, stubConfirm } from '../test/record';
import { server } from '../test/server';
import { renderWithProviders } from '../test/utils';
import { FeedListPage } from './FeedListPage';

function showFeeds(...feeds: unknown[]) {
  server.use(http.get('/api/v2/feeds', () => HttpResponse.json({ feeds })));
}

function asUser(user: unknown) {
  server.use(
    http.get('/api/v2/auth/status', () =>
      HttpResponse.json({ authenticated: true, user, needs_registration: false }),
    ),
  );
}

describe('FeedListPage', () => {
  it('Pin patches is_pinned true for an unpinned feed', async () => {
    asUser(adminUser);
    showFeeds(makeFeed({ id: 3, is_pinned: false, is_system: false }));
    const calls = recordRequests('patch', '/api/v2/feeds/3');

    renderWithProviders(<FeedListPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Pin' }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toEqual({ is_pinned: true });
  });

  it('Unpin patches is_pinned false', async () => {
    asUser(adminUser);
    showFeeds(makeFeed({ id: 3, is_pinned: true, is_system: false }));
    const calls = recordRequests('patch', '/api/v2/feeds/3');

    renderWithProviders(<FeedListPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Unpin' }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toEqual({ is_pinned: false });
  });

  it('does not offer pinning on system feeds', async () => {
    asUser(adminUser);
    showFeeds(makeFeed({ id: 3, is_system: true }));

    renderWithProviders(<FeedListPage />);
    await screen.findByText('My Library');
    expect(screen.queryByRole('button', { name: /^(Pin|Unpin)$/ })).toBeNull();
  });

  it('Delete asks first and then deletes that feed', async () => {
    asUser(adminUser);
    showFeeds(makeFeed({ id: 3, user_id: adminUser.id, is_system: false }));
    const confirm = stubConfirm(true);
    const calls = recordRequests('delete', '/api/v2/feeds/3');

    renderWithProviders(<FeedListPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Delete' }));

    expect(confirm).toHaveBeenCalledWith(expect.stringContaining('My Library'));
    await waitFor(() => expect(calls).toHaveLength(1));
  });

  it('does not delete when the confirmation is dismissed', async () => {
    asUser(adminUser);
    showFeeds(makeFeed({ id: 3, user_id: adminUser.id, is_system: false }));
    stubConfirm(false);
    const calls = recordRequests('delete', '/api/v2/feeds/3');

    renderWithProviders(<FeedListPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Delete' }));

    expect(calls).toHaveLength(0);
  });

  it("does not offer Delete on another user's feed", async () => {
    asUser(regularUser);
    showFeeds(makeFeed({ id: 3, user_id: 999, is_system: false }));

    renderWithProviders(<FeedListPage />);
    await screen.findByText('My Library');
    expect(screen.queryByRole('button', { name: 'Delete' })).toBeNull();
  });

  it('copies the RSS URL to the clipboard and confirms it did', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    asUser(adminUser);
    showFeeds(makeFeed({ id: 3, rss_url: 'https://example.com/feed/my-library.xml' }));

    renderWithProviders(<FeedListPage />);
    await userEvent.click(await screen.findByRole('button', { name: /copy rss url/i }));

    expect(writeText).toHaveBeenCalledWith('https://example.com/feed/my-library.xml');
    expect(await screen.findByRole('button', { name: /copied!/i })).toBeInTheDocument();
  });

  it('shows an empty state rather than a bare heading', async () => {
    showFeeds();
    renderWithProviders(<FeedListPage />);
    expect(await screen.findByText(/no feeds/i)).toBeInTheDocument();
  });
});
