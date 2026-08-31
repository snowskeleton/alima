import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { server } from '../test/server';
import { setCsrfCookie, stubLocation } from '../test/utils';
import { ApiError, apiFetch } from './client';

/**
 * The API client is the one piece of frontend code every page depends on, and
 * the one place a mistake is invisible in the UI until it matters: a dropped
 * CSRF header only fails on mutations, and the 401 redirect only fires when a
 * session expires.
 */

describe('apiFetch', () => {
  beforeEach(() => {
    setCsrfCookie('csrf-abc');
  });

  it('prefixes the path with /api/v2', async () => {
    let seen = '';
    server.use(
      http.get('/api/v2/books', ({ request }) => {
        seen = new URL(request.url).pathname;
        return HttpResponse.json({ books: [] });
      }),
    );

    await apiFetch('/books');
    expect(seen).toBe('/api/v2/books');
  });

  it('sends the CSRF token from the cookie', async () => {
    let token: string | null = null;
    server.use(
      http.post('/api/v2/feeds', ({ request }) => {
        token = request.headers.get('x-csrf-token');
        return HttpResponse.json({ ok: true });
      }),
    );

    await apiFetch('/feeds', { method: 'POST', body: '{}' });
    expect(token).toBe('csrf-abc');
  });

  it('url-decodes a CSRF cookie value', async () => {
    document.cookie = 'alima_csrf=a%2Bb%3Dc';
    let token: string | null = null;
    server.use(
      http.post('/api/v2/feeds', ({ request }) => {
        token = request.headers.get('x-csrf-token');
        return HttpResponse.json({});
      }),
    );

    await apiFetch('/feeds', { method: 'POST', body: '{}' });
    expect(token).toBe('a+b=c');
  });

  it('sends JSON content-type for ordinary bodies', async () => {
    let contentType: string | null = null;
    server.use(
      http.post('/api/v2/feeds', ({ request }) => {
        contentType = request.headers.get('content-type');
        return HttpResponse.json({});
      }),
    );

    await apiFetch('/feeds', { method: 'POST', body: JSON.stringify({ a: 1 }) });
    expect(contentType).toContain('application/json');
  });

  it('does NOT force JSON content-type for FormData', async () => {
    // The runtime has to set this header itself, because it must include the
    // multipart boundary. Forcing application/json makes cover and auth-file
    // uploads unparseable server-side.
    //
    // Asserted as "not application/json" rather than "is multipart": what the
    // client controls is whether it overrides the header, and the exact
    // multipart serialisation is the environment's business, not this code's.
    let contentType = '';
    server.use(
      http.post('/api/v2/feeds', ({ request }) => {
        contentType = request.headers.get('content-type') ?? '';
        return HttpResponse.json({});
      }),
    );

    const body = new FormData();
    body.append('name', 'x');
    await apiFetch('/feeds', { method: 'POST', body });

    expect(contentType).not.toContain('application/json');
  });

  it('sends cookies same-origin', async () => {
    // The session token lives in an HTTP-only cookie; without credentials every
    // request is anonymous.
    let credentials: RequestCredentials | undefined;
    const original = globalThis.fetch;
    globalThis.fetch = vi.fn((input, init) => {
      credentials = init?.credentials;
      return original(input as RequestInfo, init);
    }) as typeof fetch;

    server.use(http.get('/api/v2/books', () => HttpResponse.json({})));
    await apiFetch('/books');

    globalThis.fetch = original;
    expect(credentials).toBe('same-origin');
  });

  it('returns the parsed JSON body', async () => {
    server.use(http.get('/api/v2/books', () => HttpResponse.json({ total: 7 })));
    await expect(apiFetch<{ total: number }>('/books')).resolves.toEqual({ total: 7 });
  });

  it('returns undefined for 204 No Content', async () => {
    // Parsing an empty body as JSON throws, which would turn a successful
    // delete into an error toast.
    server.use(http.delete('/api/v2/feeds/1', () => new HttpResponse(null, { status: 204 })));
    await expect(apiFetch('/feeds/1', { method: 'DELETE' })).resolves.toBeUndefined();
  });

  describe('error handling', () => {
    it('throws ApiError carrying the status and the detail', async () => {
      server.use(
        http.get('/api/v2/books', () =>
          HttpResponse.json({ detail: 'Book not found' }, { status: 404 }),
        ),
      );

      await expect(apiFetch('/books')).rejects.toMatchObject({
        name: 'ApiError',
        status: 404,
        message: 'Book not found',
      });
    });

    it('falls back to a generic message when the body has no detail', async () => {
      server.use(
        http.get('/api/v2/books', () => HttpResponse.json({}, { status: 500 })),
      );
      await expect(apiFetch('/books')).rejects.toThrow('Request failed');
    });

    it('does not choke on a non-JSON error body', async () => {
      // A proxy 502 returns HTML; parsing it must not mask the real status.
      server.use(
        http.get('/api/v2/books', () =>
          HttpResponse.text('<html>Bad Gateway</html>', { status: 502 }),
        ),
      );

      await expect(apiFetch('/books')).rejects.toMatchObject({ status: 502 });
    });

    it('redirects to login on 401', async () => {
      const location = stubLocation();

      server.use(
        http.get('/api/v2/books', () => new HttpResponse(null, { status: 401 })),
      );

      await expect(apiFetch('/books')).rejects.toBeInstanceOf(ApiError);
      expect(location.href).toBe('/auth/login');

      location.restore();
    });

    it('does not redirect on 403', async () => {
      // A 403 means signed in but not permitted. Redirecting to login would
      // bounce an ordinary user out of the app for visiting an admin page.
      const location = stubLocation();
      const before = location.href;

      server.use(
        http.get('/api/v2/books', () =>
          HttpResponse.json({ detail: 'Admin required' }, { status: 403 }),
        ),
      );

      await expect(apiFetch('/books')).rejects.toMatchObject({ status: 403 });
      expect(location.href).toBe(before);

      location.restore();
    });
  });
});
