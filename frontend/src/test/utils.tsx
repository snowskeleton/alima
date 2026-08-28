import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within, type RenderOptions } from '@testing-library/react';
import type { ReactElement, ReactNode } from 'react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';

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
    auth,
    ...options
  }: RenderOptions & { route?: string; path?: string; auth?: unknown } = {},
) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });

  // Pages that redirect on auth state read it synchronously on first render:
  // in the real app the shell has already resolved /auth/status, so the answer
  // is in the cache. Seeding it here reproduces that, rather than testing a
  // first paint the user never sees.
  if (auth !== undefined) {
    queryClient.setQueryData(['auth'], auth);
  }

  /**
   * Renders the current path into the DOM so tests can assert on navigation.
   *
   * It doubles as a catch-all: without it, any navigate() to a path the test
   * did not register logs "No routes matched location", which is noise that
   * hides real warnings.
   */
  function LocationProbe() {
    const location = useLocation();
    return (
      <span data-testid="location" hidden>
        {location.pathname + location.search}
      </span>
    );
  }

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter
          initialEntries={[route]}
          // Opt in to the v7 behaviours now: without these every render logs
          // two deprecation warnings, which buries real output.
          future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
        >
          <LocationProbe />
          {path ? (
            <Routes>
              <Route path={path} element={children} />
              <Route path="*" element={null} />
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

/** The path (plus query string) the router is currently on. */
export function currentPath(): string {
  return screen.getByTestId('location').textContent ?? '';
}

/**
 * Queries scoped to an open modal.
 *
 * Pages routinely have a "Create Key"-style button that opens a modal and a
 * second one inside it that submits. Both are <Button>s with no explicit type,
 * so both report as submit buttons -- scoping to the dialog is the only way to
 * tell them apart.
 */
export function inModal(name?: string | RegExp) {
  return within(screen.getByRole('dialog', name ? { name } : undefined));
}

/**
 * Attach a file to a file input and fire the change React listens for.
 *
 * userEvent.upload builds the FileList through jsdom, which only accepts a
 * jsdom File -- but the app then hands that File to Node's FormData, which
 * only accepts Node's. Setting `files` directly lets the test use the same
 * File implementation the fetch layer expects.
 */
export function attachFile(input: HTMLElement, file: File) {
  Object.defineProperty(input, 'files', { value: [file], configurable: true });
  fireEvent.change(input);
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
