import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterAll, afterEach, beforeAll } from 'vitest';
import { server } from './server';

// MSW intercepts at the network boundary, so src/api/client.ts -- CSRF header,
// 401 redirect, error unwrapping -- runs for real in every test. Mocking the
// client itself would leave exactly that layer untested.
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));

afterEach(() => {
  cleanup();
  server.resetHandlers();
  document.cookie = 'alima_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT';
});

afterAll(() => server.close());
