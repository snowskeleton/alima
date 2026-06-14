import { useState } from 'react';
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
  const [copiedId, setCopiedId] = useState<number | null>(null);

  if (isLoading) return <PageSpinner />;

  const feeds = data?.feeds ?? [];

  function copyRss(feedId: number, url: string) {
    navigator.clipboard.writeText(url).then(() => {
      setCopiedId(feedId);
      setTimeout(() => setCopiedId(null), 2000);
    });
  }

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
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {feeds.map((feed) => (
            <div
              key={feed.id}
              className="bg-white rounded-lg border border-gray-200 p-4 flex flex-col gap-3 hover:shadow-md transition-shadow cursor-pointer"
              onClick={() => window.location.href = `/feed/${feed.slug}`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2 flex-wrap min-w-0">
                  <Link
                    to={`/feed/${feed.slug}`}
                    className="font-semibold text-gray-900 hover:text-indigo-600 truncate"
                    onClick={e => e.stopPropagation()}
                  >
                    {feed.name}
                    {feed.is_pinned && <span className="ml-1">📌</span>}
                  </Link>
                </div>
              </div>

              <div className="flex items-center gap-1.5 flex-wrap">
                <Badge>{feed.feed_type}</Badge>
                {feed.is_public
                  ? <Badge color="green">Public</Badge>
                  : <Badge color="yellow">Private</Badge>}
                {feed.is_system && <Badge color="blue">System</Badge>}
              </div>

              {feed.description && (
                <p className="text-sm text-gray-500 line-clamp-2">{feed.description}</p>
              )}

              <div className="flex items-center gap-2 flex-wrap mt-auto" onClick={e => e.stopPropagation()}>
                {feed.rss_url && (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => copyRss(feed.id, feed.rss_url!)}
                  >
                    {copiedId === feed.id ? 'Copied!' : 'Copy RSS URL'}
                  </Button>
                )}
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
                  <Link to={`/feeds/${feed.id}/edit`} onClick={e => e.stopPropagation()}>
                    <Button variant="ghost" size="sm">Edit</Button>
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
