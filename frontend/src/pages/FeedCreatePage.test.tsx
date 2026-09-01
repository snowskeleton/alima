import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { recordRequests } from '../test/record';
import { currentPath, renderWithProviders } from '../test/utils';
import { FeedCreatePage } from './FeedCreatePage';

// This form posts multipart/form-data, not JSON: the sibling edit form uploads
// a cover file and both share the backend route. recordRequests decodes the
// multipart body into a plain object, so assertions read like any other.

describe('FeedCreatePage', () => {
  it('posts the form to /feeds and returns to the feed list', async () => {
    const calls = recordRequests('post', '/api/v2/feeds', { id: 5 });

    renderWithProviders(<FeedCreatePage />);
    await userEvent.type(screen.getByLabelText(/name/i), 'Sci-Fi');
    await userEvent.click(screen.getByRole('button', { name: /create feed/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body.name).toBe('Sci-Fi');
    await waitFor(() => expect(currentPath()).toBe('/feeds'));
  });

  it('sends the multipart body the backend route expects, not JSON', async () => {
    // apiFetch is told `headers: {}` so the browser can set the multipart
    // boundary itself; a JSON content-type here would 422 every submission.
    const calls = recordRequests('post', '/api/v2/feeds', { id: 5 });

    renderWithProviders(<FeedCreatePage />);
    await userEvent.type(screen.getByLabelText(/name/i), 'Sci-Fi');
    await userEvent.click(screen.getByRole('button', { name: /create feed/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].headers.get('content-type')).toMatch(/multipart\/form-data/);
  });

  it('includes the smart-feed filters in the submission', async () => {
    const calls = recordRequests('post', '/api/v2/feeds', { id: 5 });

    renderWithProviders(<FeedCreatePage />);
    await userEvent.type(screen.getByLabelText(/name/i), 'Sci-Fi');
    await userEvent.click(screen.getByRole('button', { name: /create feed/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toHaveProperty('filters_json');
  });

  it('omits filters_json for a manual feed', async () => {
    // A manual feed with a filter blob attached would silently behave as a
    // smart feed on the backend.
    const calls = recordRequests('post', '/api/v2/feeds', { id: 5 });

    renderWithProviders(<FeedCreatePage />);
    await userEvent.type(screen.getByLabelText(/name/i), 'Hand-picked');
    await userEvent.selectOptions(screen.getByLabelText(/type/i), 'manual');
    await userEvent.click(screen.getByRole('button', { name: /create feed/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).not.toHaveProperty('filters_json');
  });

  it('sends is_public false when the box is unchecked', async () => {
    const calls = recordRequests('post', '/api/v2/feeds', { id: 5 });

    renderWithProviders(<FeedCreatePage />);
    await userEvent.type(screen.getByLabelText(/name/i), 'Private');
    await userEvent.click(screen.getByRole('checkbox'));
    await userEvent.click(screen.getByRole('button', { name: /create feed/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body.is_public).toBe('false');
  });

  it('does not submit with an empty name', async () => {
    const calls = recordRequests('post', '/api/v2/feeds', { id: 5 });

    renderWithProviders(<FeedCreatePage />);
    await userEvent.click(screen.getByRole('button', { name: /create feed/i }));

    expect(calls).toHaveLength(0);
  });

  it('defaults to purchase-date order and posts the chosen one', async () => {
    const calls = recordRequests('post', '/api/v2/feeds', { id: 5 });

    renderWithProviders(<FeedCreatePage />);
    const order = screen.getByLabelText(/episode order/i);
    expect(order).toHaveValue('purchase_date_desc');

    await userEvent.type(screen.getByLabelText(/name/i), 'A-Z');
    await userEvent.selectOptions(order, 'title_asc');
    await userEvent.click(screen.getByRole('button', { name: /create feed/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body.sort_order).toBe('title_asc');
  });

  it('offers the manual order once the feed type is manual', async () => {
    renderWithProviders(<FeedCreatePage />);
    const optionValues = () =>
      Array.from(screen.getByLabelText(/episode order/i).querySelectorAll('option'))
        .map(o => o.value);

    expect(optionValues()).not.toContain('manual');
    await userEvent.selectOptions(screen.getByLabelText(/type/i), 'manual');
    expect(optionValues()).toContain('manual');
  });

});
