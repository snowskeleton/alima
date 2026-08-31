import { screen, waitFor } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { adminUser, regularUser } from '../../test/handlers';
import { currentPath, renderWithProviders } from '../../test/utils';
import { AdminRoute } from './AdminRoute';
import { ProtectedRoute } from './ProtectedRoute';

/**
 * Route guards are the one place where a wrong answer exposes admin pages, so
 * they are exercised through a real nested route rather than in isolation.
 */
function renderGuard(Guard: () => JSX.Element, auth: unknown) {
  return renderWithProviders(
    <Routes>
      <Route element={<Guard />}>
        <Route path="/admin/users" element={<p>Users page</p>} />
      </Route>
      <Route path="*" element={null} />
    </Routes>,
    { route: '/admin/users', auth },
  );
}

describe('ProtectedRoute', () => {
  it('lets a signed-in user through', async () => {
    renderGuard(ProtectedRoute, {
      authenticated: true, user: regularUser, needs_registration: false,
    });

    expect(await screen.findByText('Users page')).toBeInTheDocument();
  });

  it('sends a signed-out visitor to the login page', async () => {
    renderGuard(ProtectedRoute, {
      authenticated: false, user: null, needs_registration: false,
    });

    await waitFor(() => expect(currentPath()).toBe('/auth/login'));
  });

  it('sends the very first visitor to registration instead of login', async () => {
    // With no users in the database, the login form has nobody to email.
    renderGuard(ProtectedRoute, {
      authenticated: false, user: null, needs_registration: true,
    });

    await waitFor(() => expect(currentPath()).toBe('/auth/register'));
  });
});

describe('AdminRoute', () => {
  it('lets an admin through', async () => {
    renderGuard(AdminRoute, {
      authenticated: true, user: adminUser, needs_registration: false,
    });

    expect(await screen.findByText('Users page')).toBeInTheDocument();
  });

  it('bounces a regular user back to the library', async () => {
    renderGuard(AdminRoute, {
      authenticated: true, user: regularUser, needs_registration: false,
    });

    await waitFor(() => expect(currentPath()).toBe('/library'));
    expect(screen.queryByText('Users page')).toBeNull();
  });

  it('bounces a signed-out visitor too', async () => {
    renderGuard(AdminRoute, {
      authenticated: false, user: null, needs_registration: false,
    });

    await waitFor(() => expect(currentPath()).toBe('/library'));
  });
});
