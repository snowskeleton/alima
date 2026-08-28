import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterAll, afterEach, beforeAll, vi } from 'vitest';
import { Blob as NodeBlob, File as NodeFile } from 'node:buffer';
import {
  FormData as UndiciFormData,
  Headers as UndiciHeaders,
  Request as UndiciRequest,
  Response as UndiciResponse,
  fetch as undiciFetch,
} from 'undici';
import { server } from './server';

// jsdom and Node each ship their own fetch primitives, and a jsdom FormData
// handed to Node's fetch is not recognised: it degrades to String(body), so
// every multipart upload arrives as the literal text "[object FormData]" under
// a text/plain content-type. Pinning fetch and its companion classes to one
// undici realm makes the multipart encoding real, which is the only way the
// feed forms and the import upload can be asserted on at all. They must be
// installed before server.listen() so MSW patches the fetch we just set.
globalThis.FormData = UndiciFormData as unknown as typeof globalThis.FormData;
globalThis.Headers = UndiciHeaders as unknown as typeof globalThis.Headers;
globalThis.Request = UndiciRequest as unknown as typeof globalThis.Request;
globalThis.Response = UndiciResponse as unknown as typeof globalThis.Response;
globalThis.fetch = undiciFetch as unknown as typeof globalThis.fetch;
// File and Blob come from node:buffer rather than undici, which does not
// re-export them; undici's FormData only accepts these implementations, so a
// jsdom File appended to an upload form is silently rejected.
globalThis.File = NodeFile as unknown as typeof globalThis.File;
globalThis.Blob = NodeBlob as unknown as typeof globalThis.Blob;

// Node is started without --localstorage-file, so jsdom leaves window.
// localStorage undefined and any page that remembers something across visits
// throws on render. An in-memory store is enough: tests clear it themselves.
if (!globalThis.localStorage) {
  const store = new Map<string, string>();
  globalThis.localStorage = {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => void store.set(key, String(value)),
    removeItem: (key: string) => void store.delete(key),
    clear: () => store.clear(),
    key: (index: number) => [...store.keys()][index] ?? null,
    get length() {
      return store.size;
    },
  } as Storage;
}

// MSW intercepts at the network boundary, so src/api/client.ts -- CSRF header,
// 401 redirect, error unwrapping -- runs for real in every test. Mocking the
// client itself would leave exactly that layer untested.
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));

afterEach(() => {
  cleanup();
  // Tests stub window.confirm/alert; leaving those in place would silently
  // change the behaviour of every later test in the file.
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  server.resetHandlers();
  document.cookie = 'alima_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT';
});

afterAll(() => server.close());
