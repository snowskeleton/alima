import { screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { MagicLinkSentPage } from './MagicLinkSentPage';

/** This page reads only router state, so it is rendered without the query
 * provider the other pages need. */
function renderAt(state?: { email?: string }) {
  return render(
    <MemoryRouter
      initialEntries={[{ pathname: '/auth/magic-link-sent', state }]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <MagicLinkSentPage />
    </MemoryRouter>,
  );
}

describe('MagicLinkSentPage', () => {
  it('names the address the link went to', () => {
    renderAt({ email: 'reader@example.com' });

    expect(screen.getByText('reader@example.com')).toBeInTheDocument();
  });

  it('falls back to generic wording when the page is opened directly', () => {
    // Reloading this page loses the router state; "we sent a link to
    // undefined" would read as a bug.
    renderAt(undefined);

    expect(screen.getByText('your email')).toBeInTheDocument();
  });
});
