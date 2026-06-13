import { Link } from 'react-router-dom';
import type { Book } from '../../api/types';
import { Badge } from '../ui/Badge';
import { formatDuration } from '../../utils/format';

interface BookCardProps {
  book: Book;
  view?: 'grid' | 'list' | 'compact';
  onContextMenu?: (e: React.MouseEvent, book: Book) => void;
  selected?: boolean;
  onSelect?: (bookId: number) => void;
}

function getStatusBadge(book: Book) {
  if (book.file_path) return <Badge color="green">Downloaded</Badge>;
  if (book.download_unavailable) return <Badge color="red">Unavailable</Badge>;
  if (!book.download_enabled) return <Badge color="gray">Disabled</Badge>;
  return <Badge color="yellow">Pending</Badge>;
}

function getCoverUrl(book: Book): string {
  if (book.cover_image_path) return `/files/${book.cover_image_path}`;
  if (book.cover_url) return book.cover_url;
  return '';
}

export function BookCard({ book, view = 'grid', onContextMenu, selected, onSelect }: BookCardProps) {
  const coverUrl = getCoverUrl(book);

  function handleContextMenu(e: React.MouseEvent) {
    if (onContextMenu) {
      e.preventDefault();
      onContextMenu(e, book);
    }
  }

  if (view === 'compact') {
    return (
      <Link
        to={`/library/${book.id}`}
        className={`flex items-center gap-3 py-2 px-3 hover:bg-gray-50 rounded-md ${selected ? 'bg-indigo-50' : ''}`}
        onContextMenu={handleContextMenu}
      >
        {onSelect && (
          <input
            type="checkbox"
            checked={!!selected}
            className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500 flex-shrink-0"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              onSelect(book.id);
            }}
            onChange={() => {}}
          />
        )}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-gray-900 truncate">{book.title}</p>
          <p className="text-xs text-gray-500 truncate">{book.author}</p>
        </div>
        {getStatusBadge(book)}
      </Link>
    );
  }

  if (view === 'list') {
    return (
      <Link
        to={`/library/${book.id}`}
        className="flex items-center gap-4 py-3 px-4 hover:bg-gray-50 rounded-lg border border-gray-200"
        onContextMenu={handleContextMenu}
      >
        {coverUrl ? (
          <img src={coverUrl} alt="" className="w-12 h-12 rounded object-cover flex-shrink-0" />
        ) : (
          <div className="w-12 h-12 rounded bg-gray-200 flex-shrink-0" />
        )}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-gray-900 truncate">{book.title}</p>
          <p className="text-xs text-gray-500 truncate">
            {book.author}
            {book.series && ` - ${book.series}`}
          </p>
        </div>
        <div className="text-xs text-gray-400">
          {formatDuration(book.duration_seconds)}
        </div>
        {getStatusBadge(book)}
      </Link>
    );
  }

  // Grid view
  return (
    <Link
      to={`/library/${book.id}`}
      className="group block rounded-lg border border-gray-200 overflow-hidden hover:shadow-md transition-shadow"
      onContextMenu={handleContextMenu}
    >
      <div className="aspect-square bg-gray-100 relative">
        {coverUrl ? (
          <img src={coverUrl} alt="" className="w-full h-full object-cover" />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-gray-400 text-xs">
            No Cover
          </div>
        )}
        <div className="absolute top-2 right-2">{getStatusBadge(book)}</div>
      </div>
      <div className="p-3">
        <p className="text-sm font-medium text-gray-900 truncate">{book.title}</p>
        <p className="text-xs text-gray-500 truncate">{book.author}</p>
        {book.series && (
          <p className="text-xs text-gray-400 truncate mt-0.5">{book.series}</p>
        )}
      </div>
    </Link>
  );
}
