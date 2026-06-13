import { useParams, Link, useNavigate } from 'react-router-dom';
import { useBook, useBookActions } from '../api/hooks/useBooks';
import { useAuth } from '../api/hooks/useAuth';
import { PageSpinner } from '../components/ui/Spinner';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Alert } from '../components/ui/Alert';
import { formatDuration, formatFileSize, formatDate } from '../utils/format';

export function BookDetailPage() {
  const { bookId } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const { data: book, isLoading } = useBook(bookId ? Number(bookId) : undefined);
  const actions = useBookActions();

  if (isLoading) return <PageSpinner />;
  if (!book) return <Alert type="error">Book not found</Alert>;

  const coverUrl = book.cover_image_path
    ? `/files/${book.cover_image_path}`
    : book.cover_url || '';

  return (
    <div>
      <div className="mb-4">
        <Link to="/library" className="text-sm text-indigo-600 hover:text-indigo-800">
          &larr; Back to Library
        </Link>
      </div>

      <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
        <div className="md:flex">
          {/* Cover */}
          <div className="md:w-64 flex-shrink-0">
            {coverUrl ? (
              <img src={coverUrl} alt="" className="w-full md:h-full object-cover" />
            ) : (
              <div className="w-full h-64 md:h-full bg-gray-100 flex items-center justify-center text-gray-400">
                No Cover
              </div>
            )}
          </div>

          {/* Details */}
          <div className="p-6 flex-1">
            <div className="flex items-start justify-between">
              <div>
                <h1 className="text-2xl font-bold text-gray-900">{book.title}</h1>
                {book.subtitle && (
                  <p className="text-lg text-gray-600 mt-1">{book.subtitle}</p>
                )}
              </div>
              {isAdmin && (
                <Link to={`/books/${book.id}/edit`}>
                  <Button variant="secondary" size="sm">Edit</Button>
                </Link>
              )}
            </div>

            <div className="mt-4 space-y-2 text-sm">
              {book.author && (
                <p><span className="text-gray-500">Author:</span> {book.author}</p>
              )}
              {book.narrator && (
                <p><span className="text-gray-500">Narrator:</span> {book.narrator}</p>
              )}
              {book.series && (
                <p>
                  <span className="text-gray-500">Series:</span> {book.series}
                  {book.series_position && ` #${book.series_position}`}
                </p>
              )}
              {book.publisher && (
                <p><span className="text-gray-500">Publisher:</span> {book.publisher}</p>
              )}
              {book.duration_seconds && (
                <p><span className="text-gray-500">Duration:</span> {formatDuration(book.duration_seconds)}</p>
              )}
              {book.publish_date && (
                <p><span className="text-gray-500">Published:</span> {formatDate(book.publish_date)}</p>
              )}
              <p><span className="text-gray-500">Source:</span> <Badge>{book.source}</Badge></p>
              <p><span className="text-gray-500">Added:</span> {formatDate(book.added_at)}</p>
            </div>

            {/* Download status */}
            <div className="mt-4 flex flex-wrap gap-2">
              {book.file_path ? (
                <Badge color="green">Downloaded ({formatFileSize(book.file_size)})</Badge>
              ) : book.download_unavailable ? (
                <Badge color="red">Unavailable</Badge>
              ) : !book.download_enabled ? (
                <Badge color="gray">Download Disabled</Badge>
              ) : (
                <Badge color="yellow">Pending Download</Badge>
              )}
            </div>

            {book.download_error_message && (
              <Alert type="error" className="mt-3">{book.download_error_message}</Alert>
            )}

            {book.description && (
              <div className="mt-4">
                <h3 className="text-sm font-medium text-gray-700 mb-1">Description</h3>
                <p className="text-sm text-gray-600 whitespace-pre-line">{book.description}</p>
              </div>
            )}

            {/* Actions */}
            <div className="mt-6 flex flex-wrap gap-2">
              {!book.file_path && book.source === 'audible' && (
                <Button
                  size="sm"
                  onClick={() => actions.downloadBook.mutate(book.id)}
                  disabled={actions.downloadBook.isPending}
                >
                  Download Now
                </Button>
              )}

              <Button
                variant="secondary"
                size="sm"
                onClick={() =>
                  actions.toggleDownload.mutate({
                    bookId: book.id,
                    enabled: !book.download_enabled,
                  })
                }
              >
                {book.download_enabled ? 'Disable Auto-Download' : 'Enable Auto-Download'}
              </Button>

              {book.download_unavailable && (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => actions.markAvailable.mutate(book.id)}
                >
                  Mark Available
                </Button>
              )}

              {book.file_path && (
                <>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => {
                      if (confirm('Unmatch this file? It will be moved to the unassigned folder.')) {
                        actions.unmatchBook.mutate(book.id);
                      }
                    }}
                  >
                    Unmatch File
                  </Button>
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={() => {
                      if (confirm('Delete the downloaded file? The book will remain in your library.')) {
                        actions.deleteFile.mutate(book.id);
                      }
                    }}
                  >
                    Delete File
                  </Button>
                </>
              )}

              {isAdmin && (
                <Button
                  variant="danger"
                  size="sm"
                  onClick={() => {
                    if (confirm('Delete this book and all its files permanently?')) {
                      actions.deleteBook.mutate(book.id, {
                        onSuccess: () => navigate('/library'),
                      });
                    }
                  }}
                >
                  Delete Book
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
