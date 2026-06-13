import { useState } from 'react';
import { useApiKeys, useApiKeyActions } from '../api/hooks/useAdmin';
import { PageSpinner } from '../components/ui/Spinner';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Alert } from '../components/ui/Alert';
import { EmptyState } from '../components/ui/EmptyState';
import { Modal } from '../components/ui/Modal';
import { formatDateTime } from '../utils/format';

export function ApiKeyPage() {
  const { data, isLoading } = useApiKeys();
  const { createKey, deleteKey } = useApiKeyActions();
  const [showCreate, setShowCreate] = useState(false);
  const [keyName, setKeyName] = useState('');
  const [newKey, setNewKey] = useState('');

  if (isLoading) return <PageSpinner />;

  const apiKeys = data?.api_keys ?? [];

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const result = await createKey.mutateAsync(keyName);
    setNewKey(result.key);
    setKeyName('');
    setShowCreate(false);
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">API Keys</h1>
        <Button onClick={() => setShowCreate(true)}>Create Key</Button>
      </div>

      {newKey && (
        <Alert type="warning" className="mb-4">
          <p className="font-medium">New API key created. Copy it now — it won't be shown again:</p>
          <code className="block mt-2 p-2 bg-yellow-100 rounded text-sm font-mono break-all">
            {newKey}
          </code>
          <Button
            variant="ghost"
            size="sm"
            className="mt-2"
            onClick={() => {
              navigator.clipboard.writeText(newKey);
            }}
          >
            Copy to clipboard
          </Button>
        </Alert>
      )}

      {apiKeys.length === 0 ? (
        <EmptyState
          title="No API keys"
          description="Create an API key to access the API programmatically."
          action={<Button onClick={() => setShowCreate(true)}>Create Key</Button>}
        />
      ) : (
        <div className="space-y-3">
          {apiKeys.map((key) => (
            <div key={key.id} className="bg-white rounded-lg border border-gray-200 p-4">
              <div className="flex items-center justify-between">
                <div>
                  <span className="font-medium text-gray-900">{key.name}</span>
                  <span className="text-sm text-gray-500 ml-3 font-mono">{key.key_prefix}...</span>
                  <div className="text-xs text-gray-500 mt-1">
                    Created: {formatDateTime(key.created_at)}
                  </div>
                </div>
                <Button
                  variant="danger"
                  size="sm"
                  onClick={() => {
                    if (confirm(`Delete API key "${key.name}"?`)) {
                      deleteKey.mutate(key.id);
                    }
                  }}
                >
                  Delete
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      <Modal open={showCreate} onClose={() => setShowCreate(false)} title="Create API Key">
        <form onSubmit={handleCreate} className="space-y-4">
          <Input
            label="Key Name"
            value={keyName}
            onChange={(e) => setKeyName(e.target.value)}
            placeholder="e.g. My Script"
            required
          />
          <Button type="submit" disabled={createKey.isPending}>
            {createKey.isPending ? 'Creating...' : 'Create Key'}
          </Button>
        </form>
      </Modal>
    </div>
  );
}
