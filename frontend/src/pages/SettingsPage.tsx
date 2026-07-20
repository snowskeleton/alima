import { useState, useEffect } from 'react';
import { useSettings, useSettingsActions } from '../api/hooks/useAdmin';
import { PageSpinner } from '../components/ui/Spinner';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Select } from '../components/ui/Select';
import { Alert } from '../components/ui/Alert';

export function SettingsPage() {
  const { data, isLoading } = useSettings();
  const { updateSettings, testEmail, testB2, removeDefaultCover } = useSettingsActions();
  const [form, setForm] = useState<Record<string, string>>({});
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [testEmailAddr, setTestEmailAddr] = useState('');

  useEffect(() => {
    if (data?.settings) {
      const initial: Record<string, string> = {};
      for (const [key, value] of Object.entries(data.settings)) {
        initial[key] = value ?? '';
      }
      setForm(initial);
    }
  }, [data]);

  if (isLoading) return <PageSpinner />;

  const update = (key: string, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const handleSave = async () => {
    setError('');
    try {
      await updateSettings.mutateAsync(form);
      setMessage('Settings saved.');
      setTimeout(() => setMessage(''), 3000);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Save failed');
    }
  };

  const handleTestEmail = async () => {
    setError('');
    try {
      await testEmail.mutateAsync(testEmailAddr);
      setMessage('Test email sent.');
      setTimeout(() => setMessage(''), 3000);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Test email failed');
    }
  };

  const handleTestB2 = async () => {
    setError('');
    try {
      await testB2.mutateAsync();
      setMessage('Connected to B2 successfully.');
      setTimeout(() => setMessage(''), 3000);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'B2 connection failed');
    }
  };

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Settings</h1>

      {message && <Alert type="success" className="mb-4">{message}</Alert>}
      {error && <Alert type="error" className="mb-4">{error}</Alert>}

      <div className="space-y-8">
        <section className="bg-white p-6 rounded-lg border border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">General</h2>
          <div className="space-y-4">
            <Input label="App Name" value={form.app_name ?? ''} onChange={(e) => update('app_name', e.target.value)} />
            <Input label="Domain" value={form.domain ?? ''} onChange={(e) => update('domain', e.target.value)} />
            <Input
              label="Quick Sync Interval (minutes)"
              type="number"
              value={form.quick_sync_interval_minutes ?? ''}
              onChange={(e) => update('quick_sync_interval_minutes', e.target.value)}
            />
            <Input
              label="Full Sync Interval (minutes)"
              type="number"
              value={form.full_sync_interval_minutes ?? ''}
              onChange={(e) => update('full_sync_interval_minutes', e.target.value)}
            />
            <Input
              label="Download Quality"
              value={form.download_quality ?? ''}
              onChange={(e) => update('download_quality', e.target.value)}
              placeholder="e.g. high, normal"
            />
            <Input
              label="Max Concurrent Downloads"
              type="number"
              value={form.max_concurrent_downloads ?? ''}
              onChange={(e) => update('max_concurrent_downloads', e.target.value)}
            />
            <Input
              label="Session Expire Hours"
              type="number"
              value={form.session_expire_hours ?? ''}
              onChange={(e) => update('session_expire_hours', e.target.value)}
            />
            <Input
              label="Invite Expire Days"
              type="number"
              value={form.invite_expire_days ?? ''}
              onChange={(e) => update('invite_expire_days', e.target.value)}
            />

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Default Feed Cover</label>
              {form.default_feed_cover_url ? (
                <div className="flex items-center gap-3">
                  <span className="text-sm text-gray-500 truncate">{form.default_feed_cover_url}</span>
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={() => removeDefaultCover.mutate()}
                    disabled={removeDefaultCover.isPending}
                  >
                    Remove
                  </Button>
                </div>
              ) : (
                <span className="text-sm text-gray-400">No default cover set</span>
              )}
            </div>
          </div>
        </section>

        <section className="bg-white p-6 rounded-lg border border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Email (SMTP)</h2>
          <div className="space-y-4">
            <Input label="SMTP Host" value={form.smtp_host ?? ''} onChange={(e) => update('smtp_host', e.target.value)} />
            <Input label="SMTP Port" value={form.smtp_port ?? ''} onChange={(e) => update('smtp_port', e.target.value)} />
            <Input label="SMTP Username" value={form.smtp_username ?? ''} onChange={(e) => update('smtp_username', e.target.value)} />
            <Input
              label="SMTP Password"
              type="password"
              value={form.smtp_password ?? ''}
              onChange={(e) => update('smtp_password', e.target.value)}
              placeholder="Leave blank to keep current"
            />
            <Input label="From Email" value={form.smtp_from_email ?? ''} onChange={(e) => update('smtp_from_email', e.target.value)} />
            <Input label="From Name" value={form.smtp_from_name ?? ''} onChange={(e) => update('smtp_from_name', e.target.value)} />

            <div className="flex items-end gap-2">
              <Input
                label="Test Email"
                value={testEmailAddr}
                onChange={(e) => setTestEmailAddr(e.target.value)}
                placeholder="test@example.com"
              />
              <Button
                variant="secondary"
                onClick={handleTestEmail}
                disabled={testEmail.isPending || !testEmailAddr}
              >
                {testEmail.isPending ? 'Sending...' : 'Send Test'}
              </Button>
            </div>
          </div>
        </section>

        <section className="bg-white p-6 rounded-lg border border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900 mb-1">Storage (Backblaze B2)</h2>
          <p className="text-sm text-gray-500 mb-4">
            When enabled, audiobooks are uploaded to B2 and listeners are redirected there
            instead of downloading from this server. Local files are kept either way.
          </p>
          <div className="space-y-4">
            <Select
              label="Enable B2 Storage"
              value={form.b2_enabled === 'true' ? 'true' : 'false'}
              onChange={(e) => update('b2_enabled', e.target.value)}
              options={[
                { value: 'false', label: 'Disabled — serve files from this server' },
                { value: 'true', label: 'Enabled — upload to B2 and redirect' },
              ]}
            />

            {form.b2_enabled === 'true' && (
              <>
                <Input
                  label="Bucket Name"
                  value={form.b2_bucket_name ?? ''}
                  onChange={(e) => update('b2_bucket_name', e.target.value)}
                  placeholder="my-audiobooks-bucket"
                />
                <Input
                  label="Endpoint URL"
                  value={form.b2_endpoint_url ?? ''}
                  onChange={(e) => update('b2_endpoint_url', e.target.value)}
                  placeholder="https://s3.us-west-004.backblazeb2.com"
                />
                <Input
                  label="Key ID"
                  value={form.b2_access_key_id ?? ''}
                  onChange={(e) => update('b2_access_key_id', e.target.value)}
                />
                <Input
                  label="Application Key"
                  type="password"
                  value={form.b2_secret_access_key ?? ''}
                  onChange={(e) => update('b2_secret_access_key', e.target.value)}
                  placeholder="Leave blank to keep the saved key"
                />
                <Input
                  label="Signed URL Lifetime (seconds)"
                  value={form.b2_signed_url_ttl_seconds ?? ''}
                  onChange={(e) => update('b2_signed_url_ttl_seconds', e.target.value)}
                  placeholder="3600"
                />

                <div className="flex items-center gap-3 pt-2">
                  <Button
                    variant="secondary"
                    onClick={handleTestB2}
                    disabled={testB2.isPending}
                  >
                    {testB2.isPending ? 'Testing...' : 'Test Connection'}
                  </Button>
                  <span className="text-sm text-gray-500">
                    Save your settings before testing.
                  </span>
                </div>
              </>
            )}
          </div>
        </section>

        <Button onClick={handleSave} disabled={updateSettings.isPending}>
          {updateSettings.isPending ? 'Saving...' : 'Save Settings'}
        </Button>
      </div>
    </div>
  );
}
