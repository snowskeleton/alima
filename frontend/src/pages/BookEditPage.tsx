import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useBook, useBookActions } from '../api/hooks/useBooks';
import { PageSpinner } from '../components/ui/Spinner';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Alert } from '../components/ui/Alert';

export function BookEditPage() {
  const { bookId } = useParams();
  const navigate = useNavigate();
  const { data: book, isLoading } = useBook(bookId ? Number(bookId) : undefined);
  const { updateMetadata, resetMetadata } = useBookActions();

  const [form, setForm] = useState({
    title: '', subtitle: '', author: '', narrator: '',
    series: '', series_position: '', description: '', publisher: '',
  });

  useEffect(() => {
    if (book) {
      setForm({
        title: book.metadata_override?.title || book.title || '',
        subtitle: book.metadata_override?.subtitle || book.subtitle || '',
        author: book.metadata_override?.author || book.author || '',
        narrator: book.metadata_override?.narrator || book.narrator || '',
        series: book.metadata_override?.series || book.series || '',
        series_position: book.metadata_override?.series_position || book.series_position || '',
        description: book.metadata_override?.description || book.description || '',
        publisher: book.metadata_override?.publisher || book.publisher || '',
      });
    }
  }, [book]);

  if (isLoading) return <PageSpinner />;
  if (!book) return <Alert type="error">Book not found</Alert>;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    updateMetadata.mutate(
      { bookId: book.id, data: form },
      { onSuccess: () => navigate(`/library/${book.id}`) },
    );
  };

  return (
    <div className="max-w-2xl">
      <div className="mb-4">
        <Link to={`/library/${book.id}`} className="text-sm text-indigo-600 hover:text-indigo-800">
          &larr; Back to Book
        </Link>
      </div>

      <h1 className="text-2xl font-bold text-gray-900 mb-6">Edit Metadata</h1>

      <form onSubmit={handleSubmit} className="space-y-4 bg-white p-6 rounded-lg border border-gray-200">
        <Input label="Title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
        <Input label="Subtitle" value={form.subtitle} onChange={(e) => setForm({ ...form, subtitle: e.target.value })} />
        <Input label="Author" value={form.author} onChange={(e) => setForm({ ...form, author: e.target.value })} />
        <Input label="Narrator" value={form.narrator} onChange={(e) => setForm({ ...form, narrator: e.target.value })} />
        <Input label="Series" value={form.series} onChange={(e) => setForm({ ...form, series: e.target.value })} />
        <Input label="Series Position" value={form.series_position} onChange={(e) => setForm({ ...form, series_position: e.target.value })} />
        <Input label="Publisher" value={form.publisher} onChange={(e) => setForm({ ...form, publisher: e.target.value })} />
        <div>
          <label htmlFor="book-description" className="block text-sm font-medium text-gray-700 mb-1">Description</label>
          <textarea
            id="book-description"
            className="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border px-3 py-2"
            rows={4}
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
        </div>

        <div className="flex gap-3 pt-2">
          <Button type="submit" disabled={updateMetadata.isPending}>
            {updateMetadata.isPending ? 'Saving...' : 'Save Changes'}
          </Button>
          <Button
            type="button"
            variant="secondary"
            onClick={() => {
              if (confirm('Reset metadata to original values?')) {
                resetMetadata.mutate(book.id, {
                  onSuccess: () => navigate(`/library/${book.id}`),
                });
              }
            }}
          >
            Reset to Original
          </Button>
        </div>
      </form>
    </div>
  );
}
