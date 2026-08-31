import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { recordRequests } from '../test/record';
import { server } from '../test/server';
import { attachFile, renderWithProviders } from '../test/utils';
import { ImportPage } from './ImportPage';

function audioFile(name = 'hobbit.m4b') {
  return new File(['audio'], name, { type: 'audio/mp4' });
}

/** Submit directly: jsdom's constraint validation blocks a click on the submit
 * button because it cannot see the file list attachFile installs. */
function submitForm() {
  fireEvent.submit(screen.getByRole('button', { name: /upload & import/i }).closest('form')!);
}

function showJob(job: Record<string, unknown>) {
  server.use(http.get('/api/v2/jobs/:id', () => HttpResponse.json({ id: 3, ...job })));
}

describe('ImportPage', () => {
  it('uploads the file and starts the import job', async () => {
    const calls = recordRequests('post', '/api/v2/import/upload', { job_id: 3 });
    showJob({ status: 'running', meta: { filename: 'hobbit.m4b' } });

    renderWithProviders(<ImportPage />);
    attachFile(screen.getByLabelText(/audio file/i), audioFile());
    submitForm();

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].headers.get('content-type')).toMatch(/multipart\/form-data/);
    expect(await screen.findByText(/importing/i)).toBeInTheDocument();
  });

  it('sends the metadata overrides that were filled in', async () => {
    const calls = recordRequests('post', '/api/v2/import/upload', { job_id: 3 });
    showJob({ status: 'running' });

    renderWithProviders(<ImportPage />);
    attachFile(screen.getByLabelText(/audio file/i), audioFile());
    await userEvent.type(screen.getByLabelText(/^title$/i), 'The Hobbit');
    await userEvent.type(screen.getByLabelText(/^author$/i), 'Tolkien');
    submitForm();

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body.title).toBe('The Hobbit');
    expect(calls[0].body.author).toBe('Tolkien');
  });

  it('omits the override fields left blank', async () => {
    // Sending empty strings would overwrite whatever the file's own tags say
    // with nothing, which is the opposite of "optional override".
    const calls = recordRequests('post', '/api/v2/import/upload', { job_id: 3 });
    showJob({ status: 'running' });

    renderWithProviders(<ImportPage />);
    attachFile(screen.getByLabelText(/audio file/i), audioFile());
    submitForm();

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body).not.toHaveProperty('title');
    expect(calls[0].body).not.toHaveProperty('publisher');
  });

  it('sends extract_metadata false when the box is unchecked', async () => {
    const calls = recordRequests('post', '/api/v2/import/upload', { job_id: 3 });
    showJob({ status: 'running' });

    renderWithProviders(<ImportPage />);
    attachFile(screen.getByLabelText(/audio file/i), audioFile());
    await userEvent.click(screen.getByRole('checkbox'));
    submitForm();

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body.extract_metadata).toBe('false');
  });

  it('does not upload with no file chosen', async () => {
    const calls = recordRequests('post', '/api/v2/import/upload', { job_id: 3 });

    renderWithProviders(<ImportPage />);
    submitForm();

    expect(calls).toHaveLength(0);
  });

  it('keeps the submit button disabled until a file is chosen', async () => {
    renderWithProviders(<ImportPage />);

    expect(screen.getByRole('button', { name: /upload & import/i })).toBeDisabled();
  });

  it('surfaces a rejected upload', async () => {
    recordRequests('post', '/api/v2/import/upload', { detail: 'Unsupported format' }, { status: 400 });

    renderWithProviders(<ImportPage />);
    attachFile(screen.getByLabelText(/audio file/i), audioFile('notes.txt'));
    submitForm();

    expect(await screen.findByText(/unsupported format/i)).toBeInTheDocument();
  });

  it('reports the imported book once the job completes', async () => {
    recordRequests('post', '/api/v2/import/upload', { job_id: 3 });
    showJob({ status: 'completed', result: { title: 'The Hobbit' } });

    renderWithProviders(<ImportPage />);
    attachFile(screen.getByLabelText(/audio file/i), audioFile());
    submitForm();

    expect(await screen.findByText(/import completed/i)).toBeInTheDocument();
    expect(screen.getByText(/the hobbit/i)).toBeInTheDocument();
  });

  it('reports why the import failed and offers the form again', async () => {
    recordRequests('post', '/api/v2/import/upload', { job_id: 3 });
    showJob({ status: 'failed', error_message: 'Corrupt file' });

    renderWithProviders(<ImportPage />);
    attachFile(screen.getByLabelText(/audio file/i), audioFile());
    submitForm();

    expect(await screen.findByText(/corrupt file/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /upload & import/i })).toBeInTheDocument();
  });

  it('Import Another clears the form for the next book', async () => {
    recordRequests('post', '/api/v2/import/upload', { job_id: 3 });
    showJob({ status: 'completed', result: { title: 'The Hobbit' } });

    renderWithProviders(<ImportPage />);
    attachFile(screen.getByLabelText(/audio file/i), audioFile());
    await userEvent.type(screen.getByLabelText(/^title$/i), 'The Hobbit');
    submitForm();

    await userEvent.click(await screen.findByRole('button', { name: /import another/i }));

    expect(await screen.findByLabelText(/^title$/i)).toHaveValue('');
    expect(screen.queryByText(/import completed/i)).toBeNull();
  });
});
