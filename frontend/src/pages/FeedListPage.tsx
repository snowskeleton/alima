import { Link } from 'react-router-dom';
import { useFeeds, useFeedActions } from '../api/hooks/useFeeds';
import { useAuth } from '../api/hooks/useAuth';
import { PageSpinner } from '../components/ui/Spinner';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { EmptyState } from '../components/ui/EmptyState';

export function FeedListPage() {
  const { data, isLoading } = useFeeds();
  const { user } = useAuth();
  const { deleteFeed, patchFeed } = useFeedActions();
  const isAdmin = user?.role === 'admin';

  if (isLoading) return <PageSpinner />;

  const feeds = data?.feeds ?? [];

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Feeds</h1>
        <Link to="/feeds/create">
          <Button>Create Feed</Button>
        </Link>
      </div>

      {feeds.length === 0 ? (
        <EmptyState title="No feeds" description="Create your first feed to share your library." />
      ) : (
        <div className="space-y-3">
          {feeds.map((feed) => (
            <div key={feed.id} className="bg-white rounded-lg border border-gray-200 p-4 flex items-center justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <Link to={`/feed/${feed.slug}`} className="text-sm font-medium text-gray-900 hover:text-indigo-600">
                    {feed.name}
                  </Link>
                  <Badge>{feed.feed_type}</Badge>
                  {feed.is_pinned && <Badge color="indigo">Pinned</Badge>}
                  {feed.is_system && <Badge color="blue">System</Badge>}
                  {!feed.is_public && <Badge color="yellow">Private</Badge>}
                </div>
                {feed.description && (
                  <p className="text-xs text-gray-500 mt-1">{feed.description}</p>
                )}
                {feed.rss_url && (
                  <p className="text-xs text-gray-400 mt-1 font-mono">{feed.rss_url}</p>
                )}
              </div>
              <div className="flex items-center gap-2">
                {isAdmin && !feed.is_system && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => patchFeed.mutate({ feedId: feed.id, data: { is_pinned: !feed.is_pinned } })}
                  >
                    {feed.is_pinned ? 'Unpin' : 'Pin'}
                  </Button>
                )}
                {(feed.user_id === user?.id || (isAdmin && feed.is_system)) && (
                  <Link to={`/feeds/${feed.id}/edit`}>
                    <Button variant="secondary" size="sm">Edit</Button>
                  </Link>
                )}
                {feed.user_id === user?.id && !feed.is_system && (
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={() => {
                      if (confirm(`Delete feed "${feed.name}"?`)) {
                        deleteFeed.mutate(feed.id);
                      }
                    }}
                  >
                    Delete
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
