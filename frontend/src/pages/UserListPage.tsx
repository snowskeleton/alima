import { useState } from 'react';
import { useUsers, useUserActions } from '../api/hooks/useAdmin';
import { PageSpinner } from '../components/ui/Spinner';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Input } from '../components/ui/Input';
import { Select } from '../components/ui/Select';
import { Alert } from '../components/ui/Alert';
import { EmptyState } from '../components/ui/EmptyState';
import { Modal } from '../components/ui/Modal';
import { formatDateTime } from '../utils/format';

export function UserListPage() {
  const [sort, setSort] = useState('created_desc');
  const { data, isLoading } = useUsers(sort);
  const { createUser, patchUser, deleteUser, sendLoginLink } = useUserActions();
  const [showCreate, setShowCreate] = useState(false);
  const [newEmail, setNewEmail] = useState('');
  const [newRole, setNewRole] = useState('user');
  const [message, setMessage] = useState('');

  if (isLoading) return <PageSpinner />;

  const users = data?.users ?? [];

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    await createUser.mutateAsync({ email: newEmail, role: newRole });
    setShowCreate(false);
    setNewEmail('');
    setNewRole('user');
  };

  const handleSendLink = async (userId: number) => {
    await sendLoginLink.mutateAsync(userId);
    setMessage('Login link sent.');
    setTimeout(() => setMessage(''), 3000);
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Users</h1>
        <div className="flex items-center gap-2">
          <Select
            value={sort}
            onChange={(e) => setSort(e.target.value)}
            options={[
              { value: 'created_desc', label: 'Newest first' },
              { value: 'created_asc', label: 'Oldest first' },
              { value: 'email_asc', label: 'Email A-Z' },
            ]}
          />
          <Button onClick={() => setShowCreate(true)}>Add User</Button>
        </div>
      </div>

      {message && <Alert type="success" className="mb-4">{message}</Alert>}

      {users.length === 0 ? (
        <EmptyState title="No users" />
      ) : (
        <div className="space-y-3">
          {users.map((user) => (
            <div key={user.id} className="bg-white rounded-lg border border-gray-200 p-4">
              <div className="flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-gray-900">{user.email}</span>
                    <Badge color={user.role === 'admin' ? 'indigo' : 'gray'}>
                      {user.role}
                    </Badge>
                  </div>
                  <div className="text-xs text-gray-500 mt-1">
                    Created: {formatDateTime(user.created_at)}
                    {user.last_login && <> | Last login: {formatDateTime(user.last_login)}</>}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => handleSendLink(user.id)}
                    disabled={sendLoginLink.isPending}
                  >
                    Send Login Link
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      patchUser.mutate({
                        id: user.id,
                        data: { role: user.role === 'admin' ? 'user' : 'admin' },
                      })
                    }
                  >
                    {user.role === 'admin' ? 'Demote' : 'Promote'}
                  </Button>
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={() => {
                      if (confirm(`Delete user "${user.email}"?`)) {
                        deleteUser.mutate(user.id);
                      }
                    }}
                  >
                    Delete
                  </Button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <Modal open={showCreate} onClose={() => setShowCreate(false)} title="Add User">
        <form onSubmit={handleCreate} className="space-y-4">
          <Input
            label="Email"
            type="email"
            value={newEmail}
            onChange={(e) => setNewEmail(e.target.value)}
            required
          />
          <Select
            label="Role"
            value={newRole}
            onChange={(e) => setNewRole(e.target.value)}
            options={[
              { value: 'user', label: 'User' },
              { value: 'admin', label: 'Admin' },
            ]}
          />
          <Button type="submit" disabled={createUser.isPending}>
            {createUser.isPending ? 'Creating...' : 'Create User'}
          </Button>
        </form>
      </Modal>
    </div>
  );
}
