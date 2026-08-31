import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { makeFeed } from '../test/handlers';
import { recordRequests, stubConfirm } from '../test/record';
import { server } from '../test/server';
import { attachFile, currentPath, renderWithProviders } from '../test/utils';
import { FeedEditPage } from './FeedEditPage';

function showFeed(overrides: Record<string, unknown> = {}) {
  server.use(http.get('/api/v2/feeds/:id', () => HttpResponse.json(makeFeed(overrides))));
}

function render() {
  return renderWithProviders(<FeedEditPage />, {
    route: '/feeds/3/edit',
    path: '/feeds/:feedId/edit',
  });
}

describe('FeedEditPage', () => {
  it('prefills the form from the feed it loaded', async () => {
    showFeed({ id: 3, name: 'Sci-Fi', description: 'Space books' });
    render();

    expect(await screen.findByLabelText(/name/i)).toHaveValue('Sci-Fi');
    expect(screen.getByLabelText(/description/i)).toHaveValue('Space books');
  });

  it('PUTs the edited feed and returns to the feed page', async () => {
    showFeed({ id: 3, slug: 'sci-fi' });
    const calls = recordRequests('put', '/api/v2/feeds/3');

    render();
    const name = await screen.findByLabelText(/name/i);
    await userEvent.clear(name);
    await userEvent.type(name, 'Fantasy');
    await userEvent.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body.name).toBe('Fantasy');
    expect(calls[0].headers.get('content-type')).toMatch(/multipart\/form-data/);
    await waitFor(() => expect(currentPath()).toBe('/feed/sci-fi'));
  });

  it('includes the cover image when one was picked', async () => {
    showFeed({ id: 3 });
    const calls = recordRequests('put', '/api/v2/feeds/3');
    // jsdom has no object URLs, and the page makes a preview from the file.
    URL.createObjectURL = () => 'blob:preview';

    render();
    await screen.findByLabelText(/name/i);
    attachFile(
      screen.getByLabelText(/cover image/i),
      new File(['img'], 'cover.jpg', { type: 'image/jpeg' }),
    );
    await userEvent.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toHaveProperty('cover_image');
  });

  it('omits cover_image when the user did not touch it', async () => {
    // Sending an empty part would replace the existing cover with nothing.
    showFeed({ id: 3, cover_image_path: 'covers/3.jpg' });
    const calls = recordRequests('put', '/api/v2/feeds/3');

    render();
    await userEvent.click(await screen.findByRole('button', { name: /save changes/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).not.toHaveProperty('cover_image');
  });

  it('sends the filters for a smart feed', async () => {
    showFeed({ id: 3, feed_type: 'smart', filter_criteria: null });
    const calls = recordRequests('put', '/api/v2/feeds/3');

    render();
    await userEvent.click(await screen.findByRole('button', { name: /save changes/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toHaveProperty('filters_json');
  });

  it('omits the filters for a manual feed', async () => {
    showFeed({ id: 3, feed_type: 'manual' });
    const calls = recordRequests('put', '/api/v2/feeds/3');

    render();
    await userEvent.click(await screen.findByRole('button', { name: /save changes/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).not.toHaveProperty('filters_json');
  });

  it('Remove Cover deletes the cover after confirmation', async () => {
    showFeed({ id: 3, cover_image_path: 'covers/3.jpg' });
    stubConfirm(true);
    const calls = recordRequests('delete', '/api/v2/feeds/3/cover');

    render();
    await userEvent.click(await screen.findByRole('button', { name: /remove cover/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
  });

  it('does not remove the cover when the confirmation is dismissed', async () => {
    showFeed({ id: 3, cover_image_path: 'covers/3.jpg' });
    stubConfirm(false);
    const calls = recordRequests('delete', '/api/v2/feeds/3/cover');

    render();
    await userEvent.click(await screen.findByRole('button', { name: /remove cover/i }));

    expect(calls).toHaveLength(0);
  });

  it('offers nothing to remove when the feed has no cover', async () => {
    showFeed({ id: 3, cover_image_path: null });
    render();

    await screen.findByLabelText(/name/i);
    expect(screen.queryByRole('button', { name: /remove cover/i })).toBeNull();
  });

  it('reports a missing feed rather than an empty form', async () => {
    server.use(
      http.get('/api/v2/feeds/:id', () =>
        HttpResponse.json({ detail: 'Not found' }, { status: 404 }),
      ),
    );
    render();

    expect(await screen.findByText(/feed not found/i)).toBeInTheDocument();
  });
});
