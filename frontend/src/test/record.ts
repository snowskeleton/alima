import { http, HttpResponse, type HttpHandler, type JsonBodyType } from 'msw';
import { vi } from 'vitest';
import { server } from './server';

export interface RecordedRequest {
  method: string;
  url: URL;
  /** Parsed JSON body, or undefined for GET/DELETE and empty bodies. */
  body: any;
  headers: Headers;
}

type Method = 'get' | 'post' | 'put' | 'patch' | 'delete';

/**
 * Install a handler that records every call to `path` and returns `response`.
 *
 * This is the workhorse for "does this button talk to the backend": the
 * assertion is on the recorded method, URL and body, so a button wired to the
 * wrong endpoint or sending the wrong payload fails the test even though the
 * UI looks identical either way.
 */
export function recordRequests(
  method: Method,
  path: string,
  response: JsonBodyType = { success: true },
  init: { status?: number } = {},
) {
  const calls: RecordedRequest[] = [];

  const handler: HttpHandler = http[method](path, async ({ request }) => {
    let body: unknown;
    // Several forms post multipart/form-data (the feed routes accept a cover
    // upload), where reading the body as text yields "[object FormData]"
    // rather than anything assertable. Decode those into a plain object.
    if (request.headers.get('content-type')?.includes('multipart/form-data')) {
      const form = await request.clone().formData();
      const entries: Record<string, unknown> = {};
      form.forEach((value, key) => {
        entries[key] = value;
      });
      body = entries;
    } else {
      const raw = await request.clone().text();
      if (raw) {
        try {
          body = JSON.parse(raw);
        } catch {
          body = raw;
        }
      }
    }
    calls.push({
      method: request.method,
      url: new URL(request.url),
      body,
      headers: request.headers,
    });
    return HttpResponse.json(response, { status: init.status ?? 200 });
  });

  server.use(handler);
  return calls;
}

/**
 * The most recent recorded request.
 *
 * The project targets ES2020, where Array.prototype.at does not exist, so
 * `calls.at(-1)` type-checks nowhere in this repo.
 */
export function lastRequest(calls: RecordedRequest[]): RecordedRequest {
  if (calls.length === 0) throw new Error('No request was recorded');
  return calls[calls.length - 1];
}

/** Stub window.confirm. Returns the spy so tests can assert on the prompt. */
export function stubConfirm(result = true) {
  return vi.spyOn(window, 'confirm').mockReturnValue(result);
}

/** Stub window.alert, which jsdom does not implement and otherwise throws. */
export function stubAlert() {
  return vi.spyOn(window, 'alert').mockImplementation(() => {});
}

/**
 * Replace EventSource with a stub the test drives by hand.
 *
 * jsdom has no EventSource at all, so any page using useSSE throws on render
 * without this. Returns an `emit` that pushes one server-sent event.
 */
export function stubEventSource() {
  const listeners = new Map<string, ((e: MessageEvent) => void)[]>();
  let openedUrl = '';

  class FakeEventSource {
    onopen: (() => void) | null = null;
    onerror: (() => void) | null = null;
    constructor(url: string) {
      openedUrl = url;
    }
    addEventListener(event: string, handler: (e: MessageEvent) => void) {
      listeners.set(event, [...(listeners.get(event) ?? []), handler]);
    }
    close() {}
  }

  vi.stubGlobal('EventSource', FakeEventSource);

  return {
    get url() {
      return openedUrl;
    },
    emit(event: string, data: unknown) {
      for (const handler of listeners.get(event) ?? []) {
        handler({ data: JSON.stringify(data) } as MessageEvent);
      }
    },
  };
}
