import { useState, useRef } from 'react';
import { apiFetch } from '../api/client';
import { useJob } from '../api/hooks/useJobs';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Alert } from '../components/ui/Alert';

export function ImportPage() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState('');
  const [author, setAuthor] = useState('');
  const [narrator, setNarrator] = useState('');
  const [series, setSeries] = useState('');
  const [seriesPosition, setSeriesPosition] = useState('');
  const [description, setDescription] = useState('');
  const [publisher, setPublisher] = useState('');
  const [extractMetadata, setExtractMetadata] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [jobId, setJobId] = useState<number>();
  const [error, setError] = useState('');

  const { data: job } = useJob(jobId);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;

    setUploading(true);
    setError('');

    const formData = new FormData();
    formData.append('audio_file', file);
    if (title) formData.append('title', title);
    if (author) formData.append('author', author);
    if (narrator) formData.append('narrator', narrator);
    if (series) formData.append('series', series);
    if (seriesPosition) formData.append('series_position', seriesPosition);
    if (description) formData.append('description', description);
    if (publisher) formData.append('publisher', publisher);
    formData.append('extract_metadata', String(extractMetadata));

    try {
      const result = await apiFetch<{ job_id: number }>('/import/upload', {
        method: 'POST',
        body: formData,
        headers: {},
      });
      setJobId(result.job_id);
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  const resetForm = () => {
    setFile(null);
    setTitle('');
    setAuthor('');
    setNarrator('');
    setSeries('');
    setSeriesPosition('');
    setDescription('');
    setPublisher('');
    setExtractMetadata(true);
    setJobId(undefined);
    setError('');
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  return (
    <div className="max-w-lg">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Import Book</h1>

      {error && <Alert type="error" className="mb-4">{error}</Alert>}

      {job && job.status === 'running' && (
        <Alert type="info" className="mb-4">
          Importing {String(job.meta?.filename ?? '')}...
        </Alert>
      )}

      {job && job.status === 'completed' && (
        <Alert type="success" className="mb-4">
          <p>Import completed.</p>
          {(() => {
            const r = job.result as Record<string, unknown> | null;
            return r && typeof r === 'object' && 'title' in r ? (
              <p className="text-sm mt-1">Book: {String(r.title)}</p>
            ) : null;
          })()}
          <Button variant="secondary" size="sm" className="mt-2" onClick={resetForm}>
            Import Another
          </Button>
        </Alert>
      )}

      {job && job.status === 'failed' && (
        <Alert type="error" className="mb-4">
          Import failed: {job.error_message}
          <Button variant="secondary" size="sm" className="mt-2 ml-2" onClick={resetForm}>
            Try Again
          </Button>
        </Alert>
      )}

      {(!job || job.status === 'failed') && (
        <form onSubmit={handleSubmit} className="space-y-4 bg-white p-6 rounded-lg border border-gray-200">
          <div>
            <label htmlFor="import-audio-file" className="block text-sm font-medium text-gray-700 mb-1">
              Audio File
            </label>
            <input
              id="import-audio-file"
              ref={fileInputRef}
              type="file"
              accept=".m4a,.m4b,.mp3"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded file:border-0 file:text-sm file:font-medium file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100"
              required
            />
            <p className="text-xs text-gray-400 mt-1">Supported formats: .m4a, .m4b, .mp3</p>
          </div>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={extractMetadata}
              onChange={(e) => setExtractMetadata(e.target.checked)}
            />
            Extract metadata from file
          </label>

          <hr className="border-gray-200" />
          <p className="text-sm text-gray-500">
            Optional: override extracted metadata
          </p>

          <Input label="Title" value={title} onChange={(e) => setTitle(e.target.value)} />
          <Input label="Author" value={author} onChange={(e) => setAuthor(e.target.value)} />
          <Input label="Narrator" value={narrator} onChange={(e) => setNarrator(e.target.value)} />
          <div className="grid grid-cols-2 gap-3">
            <Input label="Series" value={series} onChange={(e) => setSeries(e.target.value)} />
            <Input label="Position" value={seriesPosition} onChange={(e) => setSeriesPosition(e.target.value)} />
          </div>
          <Input label="Publisher" value={publisher} onChange={(e) => setPublisher(e.target.value)} />
          <div>
            <label htmlFor="import-description" className="block text-sm font-medium text-gray-700 mb-1">Description</label>
            <textarea
              id="import-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 text-sm"
            />
          </div>

          <Button type="submit" disabled={uploading || !file}>
            {uploading ? 'Uploading...' : 'Upload & Import'}
          </Button>
        </form>
      )}
    </div>
  );
}
