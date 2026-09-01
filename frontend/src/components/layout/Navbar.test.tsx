import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { adminUser, regularUser } from '../../test/handlers';
import { recordRequests } from '../../test/record';
import { renderWithProviders } from '../../test/utils';
import { Navbar } from './Navbar';

function render(user: unknown) {
  return renderWithProviders(<Navbar />, {
    auth: { authenticated: !!user, user, needs_registration: false },
  });
}

describe('Navbar', () => {
  it('Logout posts to the logout endpoint', async () => {
    const calls = recordRequests('post', '/api/v2/auth/logout');

    render(regularUser);
    await userEvent.click(screen.getByRole('button', { name: /logout/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
  });

  it('shows every admin link to an admin, pointed at a real route', async () => {
    render(adminUser);

    // The href matters as much as the label: a link with the right text and a
    // stale path is how the API Keys page went unreachable in the first place.
    const links: [string, string][] = [
      ['Accounts', '/admin/accounts'],
      ['Downloads', '/admin/downloads'],
      ['Users', '/admin/users'],
      ['Settings', '/admin/settings'],
      ['Import', '/admin/import'],
      ['Match', '/admin/match-books'],
      ['API Keys', '/admin/api-keys'],
      ['Audit', '/admin/audit'],
      ['Logs', '/logs'],
    ];

    for (const [label, href] of links) {
      expect(screen.getByRole('link', { name: label })).toHaveAttribute('href', href);
    }
  });

  it('shows a regular user only the pages they can actually open', async () => {
    // Every admin link is behind AdminRoute, so showing them here would only
    // offer a bounce back to the library.
    render(regularUser);

    expect(screen.getByRole('link', { name: 'Library' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Feeds' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Users' })).toBeNull();
    expect(screen.queryByRole('link', { name: 'Settings' })).toBeNull();
  });

  it('offers no logout to a signed-out visitor', async () => {
    render(null);

    expect(screen.queryByRole('button', { name: /logout/i })).toBeNull();
  });

  it('links the signed-in address to the profile page', async () => {
    render(regularUser);

    expect(screen.getByRole('link', { name: regularUser.email })).toHaveAttribute(
      'href',
      '/auth/profile',
    );
  });
});
