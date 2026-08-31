import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { adminUser } from '../test/handlers';
import { renderWithProviders } from '../test/utils';
import { ProfilePage } from './ProfilePage';

describe('ProfilePage', () => {
  it('shows the signed-in user', async () => {
    renderWithProviders(<ProfilePage />, {
      auth: { authenticated: true, user: adminUser, needs_registration: false },
    });

    expect(screen.getByText(adminUser.email)).toBeInTheDocument();
    expect(screen.getByText('admin')).toBeInTheDocument();
  });

  it('renders nothing rather than an empty template when there is no user', async () => {
    const { container } = renderWithProviders(<ProfilePage />, {
      auth: { authenticated: false, user: null, needs_registration: false },
    });

    expect(container.querySelector('h1')).toBeNull();
  });
});
