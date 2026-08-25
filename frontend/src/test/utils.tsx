import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, type RenderOptions } from '@testing-library/react';
import type { ReactElement, ReactNode } from 'react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

/**
 * Render a component inside the providers the real app supplies.
 *
 * `retry: false` matters: react-query retries failed queries three times by
 * default, so an error-state test would sit through three round trips before
 * the assertion could pass, and would look like a timeout rather than a
 * failure.
 */
export function renderWithProviders(
  ui: ReactElement,
  {
    route = '/',
    path,
    ...options
  }: RenderOptions & { route?: string; path?: string } = {},
) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter
          initialEntries={[route]}
          // Opt in to the v7 behaviours now: without these every render logs
          // two deprecation warnings, which buries real output.
          future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
        >
          {path ? (
            <Routes>
              <Route path={path} element={children} />
            </Routes>
          ) : (
            children
          )}
        </MemoryRouter>
      </QueryClientProvider>
    );
  }

  return { queryClient, ...render(ui, { wrapper: Wrapper, ...options }) };
}

/** Set the CSRF cookie the API client reads before every mutating request. */
export function setCsrfCookie(value = 'test-csrf-token') {
  document.cookie = `alima_csrf=${value}`;
}

/**
 * Replace window.location with a stub that records href assignments.
 *
 * The href must start out as a real URL: fetch resolves relative paths against
 * it, so a blank stub makes every request fail with "Invalid base URL" rather
 * than exercising the code under test.
 */
export function stubLocation() {
  const original = window.location;
  let href = original.href;

  Object.defineProperty(window, 'location', {
    configurable: true,
    value: {
      origin: original.origin,
      protocol: original.protocol,
      host: original.host,
      hostname: original.hostname,
      port: original.port,
      pathname: original.pathname,
      search: '',
      hash: '',
      assign: (value: string) => { href = value; },
      replace: (value: string) => { href = value; },
      toString: () => href,
      get href() { return href; },
      set href(value: string) { href = value; },
    },
  });

  return {
    get href() { return href; },
    restore() {
      Object.defineProperty(window, 'location', {
        configurable: true,
        value: original,
      });
    },
  };
}
