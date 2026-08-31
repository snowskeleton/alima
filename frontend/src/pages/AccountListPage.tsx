import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useAccounts, useAccountActions } from '../api/hooks/useAccounts';
import { useForceRefreshMetadata } from '../api/hooks/useAdmin';
import { apiFetch } from '../api/client';
import { useQueryClient } from '@tanstack/react-query';
import { PageSpinner } from '../components/ui/Spinner';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { EmptyState } from '../components/ui/EmptyState';
import { Alert } from '../components/ui/Alert';
import { timeAgo } from '../utils/format';

const MARKETPLACES = [
  { value: 'US', label: 'United States' },
  { value: 'UK', label: 'United Kingdom' },
  { value: 'DE', label: 'Germany' },
  { value: 'FR', label: 'France' },
  { value: 'CA', label: 'Canada' },
  { value: 'IT', label: 'Italy' },
  { value: 'AU', label: 'Australia' },
  { value: 'IN', label: 'India' },
  { value: 'JP', label: 'Japan' },
  { value: 'ES', label: 'Spain' },
];

export function AccountListPage() {
  const { data, isLoading } = useAccounts();
  const { patchAccount, deleteAccount, syncAccount, queueAll } = useAccountActions();
  const forceRefresh = useForceRefreshMetadata();
  const qc = useQueryClient();

  const [showUpload, setShowUpload] = useState(false);
  const [uploadUsername, setUploadUsername] = useState('');
  const [uploadMarketplace, setUploadMarketplace] = useState('US');
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState('');

  if (isLoading) return <PageSpinner />;

  const accounts = data?.accounts ?? [];

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uploadFile || !uploadUsername) return;
    setUploading(true);
    setUploadError('');
    try {
      const formData = new FormData();
      formData.append('username', uploadUsername);
      formData.append('marketplace', uploadMarketplace);
      formData.append('auth_file', uploadFile);
      await apiFetch('/accounts', { method: 'POST', body: formData, headers: {} });
      qc.invalidateQueries({ queryKey: ['accounts'] });
      setShowUpload(false);
      setUploadUsername('');
      setUploadFile(null);
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Audible Accounts</h1>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            onClick={() => forceRefresh.mutate(undefined)}
            disabled={forceRefresh.isPending}
          >
            {forceRefresh.isPending ? 'Refreshing…' : 'Force Refresh Metadata'}
          </Button>
          <Button variant="secondary" onClick={() => setShowUpload(v => !v)}>
            Upload Auth File
          </Button>
          <Link to="/admin/accounts/login">
            <Button>Login with Audible</Button>
          </Link>
        </div>
      </div>

      {/* Auth file upload form */}
      {showUpload && (
        <div className="bg-white rounded-lg border border-gray-200 p-5 mb-6 space-y-4">
          <h2 className="text-base font-semibold text-gray-900">Add Account — Upload Auth File</h2>
          {uploadError && <Alert type="error">{uploadError}</Alert>}
          <form onSubmit={handleUpload} className="space-y-3">
            <div>
              <label htmlFor="account-username" className="block text-sm font-medium text-gray-700 mb-1">Username</label>
              <input
                id="account-username"
                type="text"
                required
                value={uploadUsername}
                onChange={e => setUploadUsername(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label htmlFor="account-marketplace" className="block text-sm font-medium text-gray-700 mb-1">Marketplace</label>
              <select
                id="account-marketplace"
                value={uploadMarketplace}
                onChange={e => setUploadMarketplace(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white"
              >
                {MARKETPLACES.map(m => (
                  <option key={m.value} value={m.value}>{m.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="account-auth-file" className="block text-sm font-medium text-gray-700 mb-1">Auth File (.json)</label>
              <input
                id="account-auth-file"
                type="file"
                accept=".json"
                required
                onChange={e => setUploadFile(e.target.files?.[0] ?? null)}
                className="text-sm text-gray-600"
              />
              <p className="text-xs text-gray-400 mt-1">Upload your Audible authentication .json file</p>
            </div>
            <div className="flex gap-2">
              <Button type="submit" disabled={uploading}>{uploading ? 'Uploading…' : 'Add Account'}</Button>
              <Button type="button" variant="secondary" onClick={() => setShowUpload(false)}>Cancel</Button>
            </div>
          </form>
        </div>
      )}

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
                <div className="flex items-center gap-2 flex-wrap justify-end">
                  <Button variant="secondary" size="sm" onClick={() => syncAccount.mutate(account.id)} disabled={syncAccount.isPending}>Sync</Button>
                  <Button variant="secondary" size="sm" onClick={() => queueAll.mutate(account.id)}>Queue All</Button>
                  <Button variant="ghost" size="sm" onClick={() => patchAccount.mutate({ id: account.id, data: { enabled: !account.enabled } })}>
                    {account.enabled ? 'Disable' : 'Enable'}
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => patchAccount.mutate({ id: account.id, data: { downloads_enabled: !account.downloads_enabled } })}>
                    {account.downloads_enabled ? 'Stop DL' : 'Start DL'}
                  </Button>
                  <Button variant="danger" size="sm" onClick={() => { if (confirm(`Delete account "${account.username}"?`)) deleteAccount.mutate(account.id); }}>
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
