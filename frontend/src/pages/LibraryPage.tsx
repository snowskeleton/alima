import { useState } from 'react';
import { useBooks } from '../api/hooks/useBooks';
import { BookCard } from '../components/books/BookCard';
import { BookFilters } from '../components/books/BookFilters';
import { PageSpinner } from '../components/ui/Spinner';
import { EmptyState } from '../components/ui/EmptyState';
import { Button } from '../components/ui/Button';

export function LibraryPage() {
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [source, setSource] = useState('');
  const [sort, setSort] = useState('added_at');
  const [order, setOrder] = useState('desc');
  const [view, setView] = useState('grid');
  const [limit, setLimit] = useState(50);

  const { data, isLoading } = useBooks({
    search: search || undefined,
    status: status || undefined,
    source: source || undefined,
    sort,
    order,
    limit,
    offset: 0,
  });

  if (isLoading) return <PageSpinner />;

  const books = data?.books ?? [];
  const total = data?.total ?? 0;

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold text-gray-900">Library</h1>
        <span className="text-sm text-gray-500">{total} books</span>
      </div>

      <BookFilters
        search={search} onSearchChange={setSearch}
        status={status} onStatusChange={setStatus}
        source={source} onSourceChange={setSource}
        sort={sort} onSortChange={setSort}
        order={order} onOrderChange={setOrder}
        view={view} onViewChange={setView}
      />

      {books.length === 0 ? (
        <EmptyState
          title="No books found"
          description={search ? 'Try a different search term' : 'Your library is empty'}
        />
      ) : (
        <>
          <div
            className={
              view === 'grid'
                ? 'grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4'
                : 'space-y-2'
            }
          >
            {books.map((book) => (
              <BookCard key={book.id} book={book} view={view as 'grid' | 'list' | 'compact'} />
            ))}
          </div>

          {books.length < total && (
            <div className="mt-6 text-center">
              <Button variant="secondary" onClick={() => setLimit((l) => l + 50)}>
                Load More ({total - books.length} remaining)
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
