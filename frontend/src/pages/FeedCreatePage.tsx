import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { apiFetch } from '../api/client';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Select } from '../components/ui/Select';

export function FeedCreatePage() {
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [feedType, setFeedType] = useState('smart');
  const [filterType, setFilterType] = useState('');
  const [filterValue, setFilterValue] = useState('');
  const [isPublic, setIsPublic] = useState(true);
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);

    const formData = new FormData();
    formData.append('name', name);
    formData.append('description', description);
    formData.append('feed_type', feedType);
    formData.append('is_public', String(isPublic));

    if (feedType === 'smart' && filterType && filterValue) {
      formData.append('filters_json', JSON.stringify([{ type: filterType, value: filterValue }]));
    }

    try {
      await apiFetch('/feeds', { method: 'POST', body: formData, headers: {} });
      navigate('/feeds');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="max-w-lg">
      <div className="mb-4">
        <Link to="/feeds" className="text-sm text-indigo-600 hover:text-indigo-800">&larr; Back to Feeds</Link>
      </div>

      <h1 className="text-2xl font-bold text-gray-900 mb-6">Create Feed</h1>

      <form onSubmit={handleSubmit} className="space-y-4 bg-white p-6 rounded-lg border border-gray-200">
        <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} required />
        <Input label="Description" value={description} onChange={(e) => setDescription(e.target.value)} />
        <Select
          label="Type"
          value={feedType}
          onChange={(e) => setFeedType(e.target.value)}
          options={[
            { value: 'smart', label: 'Smart (auto-filtered)' },
            { value: 'manual', label: 'Manual (hand-picked)' },
          ]}
        />

        {feedType === 'smart' && (
          <div className="space-y-3 p-3 bg-gray-50 rounded-lg border border-gray-200">
            <p className="text-xs text-gray-500">Smart feeds automatically include books matching a filter.</p>
            <Select
              label="Filter by"
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
              options={[
                { value: '', label: 'All books (no filter)' },
                { value: 'author', label: 'Author' },
                { value: 'series', label: 'Series' },
                { value: 'narrator', label: 'Narrator' },
                { value: 'genre', label: 'Genre' },
              ]}
            />
            {filterType && (
              <Input
                label="Filter value"
                value={filterValue}
                onChange={(e) => setFilterValue(e.target.value)}
                placeholder="e.g. Brandon Sanderson"
              />
            )}
          </div>
        )}

        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={isPublic} onChange={(e) => setIsPublic(e.target.checked)} />
          Public feed (accessible via RSS URL)
        </label>
        <Button type="submit" disabled={saving}>{saving ? 'Creating...' : 'Create Feed'}</Button>
      </form>
    </div>
  );
}
