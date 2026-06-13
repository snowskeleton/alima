import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useBooks, useBookActions, useBulkBookActions } from '../api/hooks/useBooks';
import { useAuth } from '../api/hooks/useAuth';
import { BookCard } from '../components/books/BookCard';
import { BookFilters } from '../components/books/BookFilters';
import { PageSpinner } from '../components/ui/Spinner';
import { EmptyState } from '../components/ui/EmptyState';
import { Button } from '../components/ui/Button';
import { ContextMenu, type ContextMenuItem } from '../components/ui/ContextMenu';
import type { Book } from '../api/types';

export function LibraryPage() {
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [source, setSource] = useState('');
  const [sort, setSort] = useState('added_at');
  const [order, setOrder] = useState('desc');
  const [view, setView] = useState('grid');
  const [limit, setLimit] = useState(50);
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; book: Book } | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const lastSelectedIndex = useRef<number | null>(null);

  const navigate = useNavigate();
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const { downloadBook, toggleDownload, markAvailable, unmatchBook, deleteFile, deleteBook } = useBookActions();
  const bulkAction = useBulkBookActions();

  const { data, isLoading } = useBooks({
    search: search || undefined,
    status: status || undefined,
    source: source || undefined,
    sort,
    order,
    limit,
    offset: 0,
  });

  // Clear selection when switching away from compact view
  useEffect(() => {
    if (view !== 'compact') {
      setSelected(new Set());
    }
  }, [view]);

  if (isLoading) return <PageSpinner />;

  const books = data?.books ?? [];
  const total = data?.total ?? 0;

  function handleContextMenu(e: React.MouseEvent, book: Book) {
    setContextMenu({ x: e.clientX, y: e.clientY, book });
  }

  function handleSelect(bookId: number, shiftKey: boolean) {
    const currentIndex = books.findIndex((b) => b.id === bookId);

    if (shiftKey && lastSelectedIndex.current !== null) {
      // Shift-click: select range between last click and this one
      const start = Math.min(lastSelectedIndex.current, currentIndex);
      const end = Math.max(lastSelectedIndex.current, currentIndex);
      setSelected((prev) => {
        const next = new Set(prev);
        for (let i = start; i <= end; i++) {
          next.add(books[i].id);
        }
        return next;
      });
      // Clear text selection caused by shift-click
      window.getSelection()?.removeAllRanges();
    } else {
      // Normal click: toggle single item
      setSelected((prev) => {
        const next = new Set(prev);
        if (next.has(bookId)) {
          next.delete(bookId);
        } else {
          next.add(bookId);
        }
        return next;
      });
      lastSelectedIndex.current = currentIndex;
    }
  }

  function handleSelectAll() {
    if (selected.size === books.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(books.map((b) => b.id)));
    }
  }

  function handleBulkAction(action: string) {
    if (selected.size === 0) return;
    const ids = Array.from(selected);

    if (action === 'delete') {
      if (!confirm(`Delete ${ids.length} book(s)? This cannot be undone.`)) return;
    }

    bulkAction.mutate({ action, bookIds: ids }, {
      onSuccess: () => setSelected(new Set()),
    });
  }

  function getContextMenuItems(book: Book): ContextMenuItem[] {
    const items: ContextMenuItem[] = [
      { label: 'Open', onClick: () => navigate(`/library/${book.id}`) },
    ];

    if (!book.file_path && book.source === 'audible') {
      items.push({ label: 'Download', onClick: () => downloadBook.mutate(book.id) });
    }

    if (!book.file_path) {
      if (book.download_enabled) {
        items.push({ label: 'Disable Download', onClick: () => toggleDownload.mutate({ bookId: book.id, enabled: false }) });
      } else {
        items.push({ label: 'Enable Download', onClick: () => toggleDownload.mutate({ bookId: book.id, enabled: true }) });
      }
    }

    if (book.download_unavailable) {
      items.push({ label: 'Mark Available', onClick: () => markAvailable.mutate(book.id) });
    }

    items.push({ separator: true });

    if (book.file_path) {
      items.push({
        label: 'Unmatch File',
        onClick: () => {
          if (confirm(`Unmatch file from "${book.title}"?`)) unmatchBook.mutate(book.id);
        },
      });
      items.push({
        label: 'Delete File',
        onClick: () => {
          if (confirm(`Delete downloaded file for "${book.title}"?`)) deleteFile.mutate(book.id);
        },
      });
    }

    if (isAdmin) {
      items.push({ label: 'Edit', onClick: () => navigate(`/books/${book.id}/edit`) });
      items.push({
        label: 'Delete Book',
        variant: 'danger',
        onClick: () => {
          if (confirm(`Delete "${book.title}" permanently?`)) deleteBook.mutate(book.id);
        },
      });
    }

    return items;
  }

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
          {view === 'compact' && (
            <div className="flex items-center gap-3 py-2 px-3 border-b border-gray-200 mb-1">
              <input
                type="checkbox"
                checked={books.length > 0 && selected.size === books.length}
                ref={(el) => {
                  if (el) el.indeterminate = selected.size > 0 && selected.size < books.length;
                }}
                className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                onChange={handleSelectAll}
              />
              <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">Select All</span>
            </div>
          )}

          <div
            className={
              view === 'grid'
                ? 'grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4'
                : 'space-y-2'
            }
          >
            {books.map((book) => (
              <BookCard
                key={book.id}
                book={book}
                view={view as 'grid' | 'list' | 'compact'}
                onContextMenu={handleContextMenu}
                selected={selected.has(book.id)}
                onSelect={view === 'compact' ? handleSelect : undefined}
              />
            ))}
          </div>

          {books.length < total && (
            <div className="mt-6 text-center">
              <Button variant="secondary" onClick={() => setLimit((l) => l + 50)}>
                Load More ({total - books.length} remaining)
              </Button>
            </div>
          )}

          {view === 'compact' && selected.size > 0 && (
            <div className="sticky bottom-0 bg-white border-t border-gray-200 px-4 py-3 flex items-center gap-3 shadow-lg mt-4">
              <span className="text-sm font-medium text-gray-700">{selected.size} selected</span>
              <div className="flex gap-2 ml-auto">
                <Button size="sm" variant="secondary" onClick={() => handleBulkAction('download')}>
                  Download All
                </Button>
                <Button size="sm" variant="secondary" onClick={() => handleBulkAction('enable_download')}>
                  Enable Downloads
                </Button>
                <Button size="sm" variant="secondary" onClick={() => handleBulkAction('disable_download')}>
                  Disable Downloads
                </Button>
                {isAdmin && (
                  <Button size="sm" variant="danger" onClick={() => handleBulkAction('delete')}>
                    Delete Books
                  </Button>
                )}
              </div>
            </div>
          )}
        </>
      )}

      {contextMenu && (
        <ContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          items={getContextMenuItems(contextMenu.book)}
          onClose={() => setContextMenu(null)}
        />
      )}
    </div>
  );
}
