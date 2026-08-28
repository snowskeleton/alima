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

  it('shows every admin link to an admin', async () => {
    render(adminUser);

    for (const label of ['Accounts', 'Downloads', 'Users', 'Settings', 'Import', 'Match', 'Audit', 'Logs']) {
      expect(screen.getByRole('link', { name: label })).toBeInTheDocument();
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
