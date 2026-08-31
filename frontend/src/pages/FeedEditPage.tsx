import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useFeed, useFeedActions } from '../api/hooks/useFeeds';
import { apiFetch } from '../api/client';
import { PageSpinner } from '../components/ui/Spinner';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import {
  FeedFilterEditor,
  parseFilterCriteria,
  serializeFilters,
  type FeedFilter,
} from '../components/feeds/FeedFilterEditor';
import { Alert } from '../components/ui/Alert';

export function FeedEditPage() {
  const { feedId } = useParams();
  const navigate = useNavigate();
  const { data: feed, isLoading, refetch } = useFeed(feedId ? Number(feedId) : undefined);
  const { removeCover } = useFeedActions();

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [filters, setFilters] = useState<FeedFilter[]>([]);
  const [isPublic, setIsPublic] = useState(true);
  const [coverFile, setCoverFile] = useState<File | null>(null);
  const [coverPreview, setCoverPreview] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [removingCover, setRemovingCover] = useState(false);

  useEffect(() => {
    if (feed) {
      setName(feed.name);
      setDescription(feed.description || '');
      setIsPublic(feed.is_public);
      setFilters(parseFilterCriteria(feed.filter_criteria));
    }
  }, [feed]);

  if (isLoading) return <PageSpinner />;
  if (!feed) return <Alert type="error">Feed not found</Alert>;

  const handleCoverChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] ?? null;
    setCoverFile(file);
    if (file) {
      setCoverPreview(URL.createObjectURL(file));
    }
  };

  const handleRemoveCover = async () => {
    if (!confirm('Remove cover image?')) return;
    setRemovingCover(true);
    try {
      await removeCover.mutateAsync(feed.id);
      await refetch();
    } finally {
      setRemovingCover(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);

    const formData = new FormData();
    formData.append('name', name);
    formData.append('description', description);
    formData.append('is_public', String(isPublic));

    if (feed.feed_type === 'smart') {
      formData.append('filters_json', serializeFilters(filters));
    }

    if (coverFile) {
      formData.append('cover_image', coverFile);
    }

    try {
      await apiFetch(`/feeds/${feed.id}`, { method: 'PUT', body: formData, headers: {} });
      navigate(`/feed/${feed.slug}`);
    } finally {
      setSaving(false);
    }
  };

  const currentCoverUrl = feed.cover_image_path ? `/files/${feed.cover_image_path}` : null;

  return (
    <div className="max-w-lg">
      <div className="mb-4">
        <Link to="/feeds" className="text-sm text-indigo-600 hover:text-indigo-800">&larr; Back to Feeds</Link>
      </div>

      <h1 className="text-2xl font-bold text-gray-900 mb-6">Edit Feed</h1>

      <form onSubmit={handleSubmit} className="space-y-4 bg-white p-6 rounded-lg border border-gray-200">
        <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} required />
        <Input label="Description" value={description} onChange={(e) => setDescription(e.target.value)} />

        {feed.feed_type === 'smart' && (
          <FeedFilterEditor filters={filters} onChange={setFilters} />
        )}

        {/* Cover image */}
        <div className="space-y-2">
          <label htmlFor="feed-cover-image" className="block text-sm font-medium text-gray-700">Cover Image</label>
          {(coverPreview || currentCoverUrl) && (
            <div className="flex items-start gap-3">
              <img
                src={coverPreview ?? currentCoverUrl!}
                alt="Cover"
                className="w-24 h-24 object-cover rounded-lg border border-gray-200"
              />
              {!coverPreview && currentCoverUrl && (
                <Button
                  type="button"
                  variant="danger"
                  size="sm"
                  onClick={handleRemoveCover}
                  disabled={removingCover}
                >
                  {removingCover ? 'Removing…' : 'Remove Cover'}
                </Button>
              )}
            </div>
          )}
          <input
            id="feed-cover-image"
            type="file"
            accept="image/jpeg,image/png,image/webp"
            onChange={handleCoverChange}
            className="text-sm text-gray-600"
          />
          <p className="text-xs text-gray-400">Recommended: 3000×3000px JPEG (max 10MB)</p>
        </div>

        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={isPublic} onChange={(e) => setIsPublic(e.target.checked)} />
          Public feed
        </label>
        <Button type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save Changes'}</Button>
      </form>
    </div>
  );
}
