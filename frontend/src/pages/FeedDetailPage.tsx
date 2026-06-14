import { useState, useMemo } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useFeedBySlug } from '../api/hooks/useFeeds';
import { useAuth } from '../api/hooks/useAuth';
import { PageSpinner } from '../components/ui/Spinner';
import { Alert } from '../components/ui/Alert';
import { BookCard } from '../components/books/BookCard';
import { EmptyState } from '../components/ui/EmptyState';

function CoverArt({ path, name }: { path: string | null; name: string }) {
  if (path) {
    return (
      <img
        src={`/files/${path}`}
        alt={name}
        className="w-full h-full object-cover"
      />
    );
  }
  return (
    <div className="w-full h-full flex items-center justify-center text-7xl"
      style={{ background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' }}>
      📻
    </div>
  );
}

function SubscribeSection({ rssUrl }: { rssUrl: string }) {
  const [copied, setCopied] = useState(false);

  function copy() {
    navigator.clipboard.writeText(rssUrl).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  const encodedUrl = encodeURIComponent(rssUrl);

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-6 space-y-5">
      <h2 className="text-lg font-semibold text-gray-900">Subscribe</h2>

      <div className="flex gap-3 flex-wrap">
        <a
          href={`overcast://x-callback-url/add?url=${encodedUrl}`}
          className="flex items-center gap-3 px-4 py-3 border-2 border-gray-200 rounded-lg hover:border-indigo-400 hover:bg-gray-50 transition-all hover:-translate-y-0.5 hover:shadow-md flex-1 min-w-48"
        >
          <img src="/static/images/overcast-icon.png" alt="Overcast" className="w-10 h-10 rounded-lg" />
          <span className="font-medium text-gray-800">Subscribe in Overcast</span>
        </a>
        <a
          href={`podcast://${rssUrl}`}
          className="flex items-center gap-3 px-4 py-3 border-2 border-gray-200 rounded-lg hover:border-indigo-400 hover:bg-gray-50 transition-all hover:-translate-y-0.5 hover:shadow-md flex-1 min-w-48"
        >
          <img src="/static/images/apple-podcasts-icon.svg" alt="Apple Podcasts" className="w-10 h-10 rounded-lg" />
          <span className="font-medium text-gray-800">Subscribe in Apple Podcasts</span>
        </a>
      </div>

      <div className="relative text-center before:absolute before:inset-y-1/2 before:left-0 before:right-0 before:h-px before:bg-gray-200">
        <span className="relative bg-white px-3 text-xs text-gray-400 uppercase tracking-wider">or copy the RSS URL</span>
      </div>

      <div className="flex gap-2">
        <input
          type="text"
          readOnly
          value={rssUrl}
          className="flex-1 px-3 py-2 border border-gray-300 rounded-lg font-mono text-sm text-gray-600 bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          onClick={(e) => (e.target as HTMLInputElement).select()}
        />
        <button
          onClick={copy}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            copied
              ? 'bg-green-600 text-white'
              : 'bg-indigo-600 text-white hover:bg-indigo-700'
          }`}
        >
          {copied ? 'Copied!' : 'Copy'}
        </button>
      </div>
    </div>
  );
}

type SortKey = 'added_at' | 'title' | 'author' | 'series' | 'duration_seconds';

export function FeedDetailPage() {
  const { slug } = useParams();
  const { data: feed, isLoading } = useFeedBySlug(slug);
  const { user } = useAuth();

  const [search, setSearch] = useState('');
  const [sort, setSort] = useState<SortKey>('added_at');
  const [order, setOrder] = useState<'asc' | 'desc'>('desc');

  const books = feed?.books ?? [];

  const filtered = useMemo(() => {
    let result = [...books];

    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter(b =>
        b.title?.toLowerCase().includes(q) ||
        b.author?.toLowerCase().includes(q) ||
        b.series?.toLowerCase().includes(q) ||
        b.narrator?.toLowerCase().includes(q)
      );
    }

    result.sort((a, b) => {
      const av = (a as unknown as Record<string, unknown>)[sort] ?? '';
      const bv = (b as unknown as Record<string, unknown>)[sort] ?? '';
      const cmp = String(av).localeCompare(String(bv), undefined, { numeric: true });
      return order === 'asc' ? cmp : -cmp;
    });

    return result;
  }, [books, search, sort, order]);

  if (isLoading) return <PageSpinner />;
  if (!feed) return <Alert type="error">Feed not found</Alert>;

  const canEdit = user && (
    user.id === feed.user_id ||
    (user.role === 'admin' && feed.is_system)
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white rounded-lg border border-gray-200 p-6 flex gap-6 items-start">
        <div className="w-48 h-48 shrink-0 rounded-lg overflow-hidden shadow-md">
          <CoverArt path={feed.cover_image_path} name={feed.name} />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-4 mb-2">
            <h1 className="text-2xl font-bold text-gray-900 leading-tight">{feed.name}</h1>
            {canEdit && (
              <Link
                to={`/feeds/${feed.id}/edit`}
                className="shrink-0 px-3 py-1.5 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 transition-colors"
              >
                Edit Feed
              </Link>
            )}
          </div>

          {feed.description && (
            <p className="text-gray-600 leading-relaxed mb-3">{feed.description}</p>
          )}

          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-sm text-gray-500">
              {search.trim()
                ? `${filtered.length} of ${books.length} episodes`
                : `${books.length} episode${books.length !== 1 ? 's' : ''}`}
            </span>
            {feed.is_system && (
              <span className="inline-flex items-center rounded-full bg-indigo-100 px-2.5 py-0.5 text-xs font-medium text-indigo-700">
                System Feed
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Subscribe */}
      {feed.rss_url && <SubscribeSection rssUrl={feed.rss_url} />}

      {/* Search + sort */}
      <div className="flex gap-2 flex-wrap items-center">
        <input
          type="text"
          placeholder="Search by title, author, series, or narrator…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="flex-1 min-w-64 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
        <select
          value={sort}
          onChange={e => setSort(e.target.value as SortKey)}
          className="px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          <option value="added_at">Date Added</option>
          <option value="title">Title</option>
          <option value="author">Author</option>
          <option value="series">Series</option>
          <option value="duration_seconds">Duration</option>
        </select>
        <button
          onClick={() => setOrder(o => o === 'asc' ? 'desc' : 'asc')}
          className="px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white hover:bg-gray-50 font-medium"
          title={order === 'asc' ? 'Ascending' : 'Descending'}
        >
          {order === 'asc' ? '↑' : '↓'}
        </button>
        {search && (
          <button
            onClick={() => setSearch('')}
            className="px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white hover:bg-gray-50 text-gray-600"
          >
            Clear
          </button>
        )}
      </div>

      {/* Episodes */}
      {filtered.length === 0 ? (
        <EmptyState
          title={search ? `No episodes match "${search}"` : 'No episodes in this feed'}
        />
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
          {filtered.map(book => (
            <BookCard key={book.id} book={book} />
          ))}
        </div>
      )}
    </div>
  );
}
