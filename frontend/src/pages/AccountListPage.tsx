import { Link } from 'react-router-dom';
import { useAccounts, useAccountActions } from '../api/hooks/useAccounts';
import { PageSpinner } from '../components/ui/Spinner';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { EmptyState } from '../components/ui/EmptyState';
import { timeAgo } from '../utils/format';

export function AccountListPage() {
  const { data, isLoading } = useAccounts();
  const { patchAccount, deleteAccount, syncAccount, queueAll } = useAccountActions();

  if (isLoading) return <PageSpinner />;

  const accounts = data?.accounts ?? [];

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Audible Accounts</h1>
        <Link to="/admin/accounts/login">
          <Button>Add Account</Button>
        </Link>
      </div>

      {accounts.length === 0 ? (
        <EmptyState
          title="No accounts"
          description="Add an Audible account to start syncing your library."
          action={<Link to="/admin/accounts/login"><Button>Add Account</Button></Link>}
        />
      ) : (
        <div className="space-y-3">
          {accounts.map((account) => (
            <div key={account.id} className="bg-white rounded-lg border border-gray-200 p-4">
              <div className="flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-gray-900">{account.username}</span>
                    <Badge>{account.marketplace.toUpperCase()}</Badge>
                    {account.enabled ? <Badge color="green">Enabled</Badge> : <Badge color="gray">Disabled</Badge>}
                    {account.downloads_enabled ? <Badge color="blue">Downloads On</Badge> : <Badge color="gray">Downloads Off</Badge>}
                  </div>
                  <p className="text-xs text-gray-500 mt-1">
                    Last synced: {timeAgo(account.last_sync_timestamp)}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => syncAccount.mutate(account.id)}
                    disabled={syncAccount.isPending}
                  >
                    Sync
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => queueAll.mutate(account.id)}
                  >
                    Queue All
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => patchAccount.mutate({ id: account.id, data: { enabled: !account.enabled } })}
                  >
                    {account.enabled ? 'Disable' : 'Enable'}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => patchAccount.mutate({ id: account.id, data: { downloads_enabled: !account.downloads_enabled } })}
                  >
                    {account.downloads_enabled ? 'Stop DL' : 'Start DL'}
                  </Button>
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={() => {
                      if (confirm(`Delete account "${account.username}"?`)) {
                        deleteAccount.mutate(account.id);
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
    </div>
  );
}
