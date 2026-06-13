import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../api/client';
import { PageSpinner } from '../components/ui/Spinner';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Alert } from '../components/ui/Alert';
import { EmptyState } from '../components/ui/EmptyState';

interface MatchCandidate {
  book_id: number;
  title: string;
  author: string;
  score: number;
}

interface UnmatchedFile {
  filename: string;
  file_path: string;
  candidates: MatchCandidate[];
}

export function MatchBooksPage() {
  const qc = useQueryClient();
  const [message, setMessage] = useState('');
  const [selections, setSelections] = useState<Record<string, number>>({});

  const { data, isLoading } = useQuery<{ matches: UnmatchedFile[] }>({
    queryKey: ['match-books'],
    queryFn: () => apiFetch('/match-books/matches'),
  });

  const confirmMatch = useMutation({
    mutationFn: (body: { filename: string; book_id: number }) =>
      apiFetch('/match-books/confirm', { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['match-books'] });
      setMessage('Match confirmed.');
      setTimeout(() => setMessage(''), 3000);
    },
  });

  const importAsNew = useMutation({
    mutationFn: (filename: string) =>
      apiFetch('/match-books/import', { method: 'POST', body: JSON.stringify({ filename }) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['match-books'] });
      setMessage('Imported as new book.');
      setTimeout(() => setMessage(''), 3000);
    },
  });

  const batchConfirm = useMutation({
    mutationFn: (matches: { filename: string; book_id: number }[]) =>
      apiFetch<{ confirmed: number; total: number }>('/match-books/batch-confirm', {
        method: 'POST',
        body: JSON.stringify({ matches }),
      }),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['match-books'] });
      const result = data as { confirmed: number; total: number };
      setMessage(`Confirmed ${result.confirmed}/${result.total} matches.`);
      setSelections({});
      setTimeout(() => setMessage(''), 3000);
    },
  });

  const deleteFile = useMutation({
    mutationFn: (filename: string) =>
      apiFetch(`/match-books/${encodeURIComponent(filename)}`, { method: 'DELETE' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['match-books'] });
      setMessage('File deleted.');
      setTimeout(() => setMessage(''), 3000);
    },
  });

  if (isLoading) return <PageSpinner />;

  const matches = data?.matches ?? [];

  const handleBatchConfirm = () => {
    const batch = Object.entries(selections).map(([filename, book_id]) => ({
      filename,
      book_id,
    }));
    if (batch.length === 0) return;
    batchConfirm.mutate(batch);
  };

  const selectionsCount = Object.keys(selections).length;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Match Books</h1>
        {selectionsCount > 0 && (
          <Button onClick={handleBatchConfirm} disabled={batchConfirm.isPending}>
            {batchConfirm.isPending
              ? 'Confirming...'
              : `Confirm ${selectionsCount} Selected`}
          </Button>
        )}
      </div>

      {message && <Alert type="success" className="mb-4">{message}</Alert>}

      {matches.length === 0 ? (
        <EmptyState
          title="No unmatched files"
          description="All files in the library are matched to books."
        />
      ) : (
        <div className="space-y-4">
          {matches.map((file) => (
            <div
              key={file.filename}
              className="bg-white rounded-lg border border-gray-200 p-4"
            >
              <div className="flex items-start justify-between mb-3">
                <div>
                  <span className="font-medium text-gray-900">{file.filename}</span>
                  <div className="text-xs text-gray-400 font-mono mt-1 truncate">
                    {file.file_path}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => importAsNew.mutate(file.filename)}
                    disabled={importAsNew.isPending}
                  >
                    Import as New
                  </Button>
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={() => {
                      if (confirm(`Delete "${file.filename}"?`)) {
                        deleteFile.mutate(file.filename);
                      }
                    }}
                    disabled={deleteFile.isPending}
                  >
                    Delete
                  </Button>
                </div>
              </div>

              {file.candidates.length > 0 ? (
                <div className="space-y-1">
                  <p className="text-xs text-gray-500 mb-2">Possible matches:</p>
                  {file.candidates.map((candidate) => (
                    <div
                      key={candidate.book_id}
                      className={`flex items-center justify-between p-2 rounded text-sm ${
                        selections[file.filename] === candidate.book_id
                          ? 'bg-indigo-50 border border-indigo-200'
                          : 'bg-gray-50 hover:bg-gray-100'
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <input
                          type="radio"
                          name={`match-${file.filename}`}
                          checked={selections[file.filename] === candidate.book_id}
                          onChange={() =>
                            setSelections((prev) => ({
                              ...prev,
                              [file.filename]: candidate.book_id,
                            }))
                          }
                        />
                        <span className="text-gray-900">{candidate.title}</span>
                        <span className="text-gray-500">by {candidate.author}</span>
                        <Badge color={candidate.score > 0.8 ? 'green' : candidate.score > 0.5 ? 'yellow' : 'red'}>
                          {Math.round(candidate.score * 100)}%
                        </Badge>
                      </div>
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() =>
                          confirmMatch.mutate({
                            filename: file.filename,
                            book_id: candidate.book_id,
                          })
                        }
                        disabled={confirmMatch.isPending}
                      >
                        Confirm
                      </Button>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-gray-400">No matching candidates found.</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
