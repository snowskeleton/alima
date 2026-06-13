import { useParams } from 'react-router-dom';
import { useFeedBySlug } from '../api/hooks/useFeeds';
import { PageSpinner } from '../components/ui/Spinner';
import { Alert } from '../components/ui/Alert';
import { BookCard } from '../components/books/BookCard';
import { EmptyState } from '../components/ui/EmptyState';

export function FeedDetailPage() {
  const { slug } = useParams();
  const { data: feed, isLoading } = useFeedBySlug(slug);

  if (isLoading) return <PageSpinner />;
  if (!feed) return <Alert type="error">Feed not found</Alert>;

  const books = feed.books ?? [];

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900">{feed.name}</h1>
      {feed.description && <p className="text-gray-600 mt-1">{feed.description}</p>}
      {feed.rss_url && (
        <p className="text-xs text-gray-400 mt-2 font-mono">RSS: {feed.rss_url}</p>
      )}

      <div className="mt-6">
        {books.length === 0 ? (
          <EmptyState title="No books in this feed" />
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
            {books.map((book) => (
              <BookCard key={book.id} book={book} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
