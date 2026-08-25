import { http, HttpResponse } from 'msw';

/**
 * Default happy-path handlers.
 *
 * `onUnhandledRequest: 'error'` in setup.ts means any request a test does not
 * account for fails loudly, so this file is the record of what the frontend
 * actually calls. Individual tests override with server.use(...).
 */

export const adminUser = {
  id: 1,
  email: 'admin@example.com',
  role: 'admin',
  receive_notifications: true,
  created_at: '2024-01-01T00:00:00',
  last_login: '2024-01-02T00:00:00',
};

export const regularUser = { ...adminUser, id: 2, email: 'user@example.com', role: 'user' };

export function makeBook(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    asin: 'B000000001',
    source: 'audible',
    title: 'The Hobbit',
    subtitle: null,
    author: 'J.R.R. Tolkien',
    narrator: 'Rob Inglis',
    series: null,
    series_position: null,
    description: 'A tale.',
    publisher: null,
    publish_date: null,
    duration_seconds: 39600,
    genres: null,
    cover_image_path: null,
    cover_url: null,
    file_path: null,
    file_size: null,
    file_format: null,
    download_enabled: true,
    download_unavailable: false,
    download_error_message: null,
    metadata_source: 'audible',
    metadata_override: null,
    added_at: '2024-01-01T00:00:00',
    downloaded_at: null,
    purchased_at: null,
    audible_account_id: 1,
    ...overrides,
  };
}

export function makeFeed(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    user_id: 1,
    name: 'My Library',
    description: null,
    feed_type: 'manual',
    filter_criteria: null,
    is_public: false,
    is_system: false,
    is_pinned: false,
    cover_image_path: null,
    slug: 'my-library',
    created_at: '2024-01-01T00:00:00',
    updated_at: '2024-01-01T00:00:00',
    rss_url: 'https://example.com/feed/my-library.xml',
    ...overrides,
  };
}

export const handlers = [
  http.get('/api/v2/auth/status', () =>
    HttpResponse.json({ authenticated: true, user: adminUser, needs_registration: false }),
  ),
  http.get('/api/v2/auth/profile', () => HttpResponse.json(adminUser)),
  http.get('/api/v2/books', () =>
    HttpResponse.json({ books: [makeBook()], total: 1, offset: 0, limit: 50 }),
  ),
  http.get('/api/v2/books/:id', () => HttpResponse.json(makeBook())),
  http.get('/api/v2/feeds', () => HttpResponse.json({ feeds: [makeFeed()] })),
  http.get('/api/v2/feeds/:id', () => HttpResponse.json(makeFeed())),
  http.get('/api/v2/users', () => HttpResponse.json({ users: [adminUser] })),
];
