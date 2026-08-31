import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { adminUser, regularUser } from '../test/handlers';
import { lastRequest, recordRequests, stubConfirm } from '../test/record';
import { server } from '../test/server';
import { inModal, renderWithProviders } from '../test/utils';
import { UserListPage } from './UserListPage';

function showUsers(...users: unknown[]) {
  server.use(http.get('/api/v2/users', () => HttpResponse.json({ users })));
}

describe('UserListPage', () => {
  it('Add User posts the email and role from the modal', async () => {
    showUsers(adminUser);
    const calls = recordRequests('post', '/api/v2/users', { id: 9 });

    renderWithProviders(<UserListPage />);
    await userEvent.click(await screen.findByRole('button', { name: /add user/i }));
    await userEvent.type(inModal().getByLabelText('Email'), 'new@example.com');
    await userEvent.selectOptions(inModal().getByLabelText(/role/i), 'admin');
    await userEvent.click(inModal().getByRole('button', { name: /create user/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toEqual({ email: 'new@example.com', role: 'admin' });
  });

  it('closes the modal once the user is created', async () => {
    showUsers(adminUser);
    recordRequests('post', '/api/v2/users', { id: 9 });

    renderWithProviders(<UserListPage />);
    await userEvent.click(await screen.findByRole('button', { name: /add user/i }));
    await userEvent.type(inModal().getByLabelText('Email'), 'new@example.com');
    await userEvent.click(inModal().getByRole('button', { name: /create user/i }));

    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /create user/i })).toBeNull(),
    );
  });

  it('Promote patches the role to admin', async () => {
    showUsers(regularUser);
    const calls = recordRequests('patch', `/api/v2/users/${regularUser.id}`);

    renderWithProviders(<UserListPage />);
    await userEvent.click(await screen.findByRole('button', { name: /promote/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toEqual({ role: 'admin' });
  });

  it('Demote patches the role back to user', async () => {
    showUsers(adminUser);
    const calls = recordRequests('patch', `/api/v2/users/${adminUser.id}`);

    renderWithProviders(<UserListPage />);
    await userEvent.click(await screen.findByRole('button', { name: /demote/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toEqual({ role: 'user' });
  });

  it('Send Login Link posts to that user and reports success', async () => {
    showUsers(regularUser);
    const calls = recordRequests('post', `/api/v2/users/${regularUser.id}/send-login-link`);

    renderWithProviders(<UserListPage />);
    await userEvent.click(await screen.findByRole('button', { name: /send login link/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(await screen.findByText(/login link sent/i)).toBeInTheDocument();
  });

  it('toggles the email-alerts flag for an admin', async () => {
    showUsers({ ...adminUser, receive_notifications: false });
    const calls = recordRequests('patch', `/api/v2/users/${adminUser.id}`);

    renderWithProviders(<UserListPage />);
    await userEvent.click(await screen.findByRole('checkbox', { name: /email alerts/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).toEqual({ receive_notifications: true });
  });

  it('does not offer email alerts to non-admins', async () => {
    // The setting only means anything for admins; showing it to a regular user
    // promises a notification that will never arrive.
    showUsers(regularUser);

    renderWithProviders(<UserListPage />);
    await screen.findByText(regularUser.email);
    expect(screen.queryByRole('checkbox', { name: /email alerts/i })).toBeNull();
  });

  it('Delete names the user in the prompt and deletes on confirm', async () => {
    showUsers(regularUser);
    const confirm = stubConfirm(true);
    const calls = recordRequests('delete', `/api/v2/users/${regularUser.id}`);

    renderWithProviders(<UserListPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Delete' }));

    expect(confirm).toHaveBeenCalledWith(expect.stringContaining(regularUser.email));
    await waitFor(() => expect(calls).toHaveLength(1));
  });

  it('does not delete when the confirmation is dismissed', async () => {
    showUsers(regularUser);
    stubConfirm(false);
    const calls = recordRequests('delete', `/api/v2/users/${regularUser.id}`);

    renderWithProviders(<UserListPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Delete' }));

    expect(calls).toHaveLength(0);
  });

  it('refetches with the chosen sort order', async () => {
    const calls = recordRequests('get', '/api/v2/users', { users: [regularUser] });

    renderWithProviders(<UserListPage />);
    await screen.findByText(regularUser.email);
    await userEvent.selectOptions(screen.getByRole('combobox'), 'email_asc');

    await waitFor(() =>
      expect(lastRequest(calls).url.searchParams.get('sort')).toBe('email_asc'),
    );
  });
});
