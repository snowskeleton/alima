import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useFeed } from '../api/hooks/useFeeds';
import { apiFetch } from '../api/client';
import { PageSpinner } from '../components/ui/Spinner';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Alert } from '../components/ui/Alert';

export function FeedEditPage() {
  const { feedId } = useParams();
  const navigate = useNavigate();
  const { data: feed, isLoading } = useFeed(feedId ? Number(feedId) : undefined);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [isPublic, setIsPublic] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (feed) {
      setName(feed.name);
      setDescription(feed.description || '');
      setIsPublic(feed.is_public);
    }
  }, [feed]);

  if (isLoading) return <PageSpinner />;
  if (!feed) return <Alert type="error">Feed not found</Alert>;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);

    const formData = new FormData();
    formData.append('name', name);
    formData.append('description', description);
    formData.append('is_public', String(isPublic));

    try {
      await apiFetch(`/feeds/${feed.id}`, {
        method: 'PUT',
        body: formData,
        headers: {},
      });
      navigate(`/feed/${feed.slug}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="max-w-lg">
      <div className="mb-4">
        <Link to="/feeds" className="text-sm text-indigo-600 hover:text-indigo-800">&larr; Back to Feeds</Link>
      </div>

      <h1 className="text-2xl font-bold text-gray-900 mb-6">Edit Feed</h1>

      <form onSubmit={handleSubmit} className="space-y-4 bg-white p-6 rounded-lg border border-gray-200">
        <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} required />
        <Input label="Description" value={description} onChange={(e) => setDescription(e.target.value)} />
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={isPublic} onChange={(e) => setIsPublic(e.target.checked)} />
          Public feed
        </label>
        <Button type="submit" disabled={saving}>{saving ? 'Saving...' : 'Save Changes'}</Button>
      </form>
    </div>
  );
}
