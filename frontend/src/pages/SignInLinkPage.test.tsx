import { act, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { recordRequests } from '../test/record';
import { server } from '../test/server';
import { renderWithProviders } from '../test/utils';
import { SignInLinkPage, type SigninLinkState } from './SignInLinkPage';

const BASE = '/api/v2/signin-links/tok123';

function linkState(overrides: Partial<SigninLinkState> = {}): SigninLinkState {
  return {
    status: 'ready',
    marketplace: 'us',
    code_url: 'https://www.amazon.com/code',
    reauth: false,
    account_name: null,
    ...overrides,
  };
}

const WAITING = linkState({ status: 'waiting', code: 'AB12C', code_expires_in: 590, poll_interval: 5 });

function showLink(state: SigninLinkState) {
  server.use(http.get(BASE, () => HttpResponse.json(state)));
}

function render() {
  return renderWithProviders(<SignInLinkPage />, { route: '/signin/tok123', path: '/signin/:token' });
}

let writeText: ReturnType<typeof vi.fn>;

beforeEach(() => {
  writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText }, configurable: true,
  });
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('SignInLinkPage', () => {
  it('offers to get a code without contacting Amazon on load', async () => {
    showLink(linkState());
    const codeCalls = recordRequests('post', `${BASE}/code`, WAITING);

    render();

    expect(await screen.findByRole('heading', { name: /connect your audible account/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /get my code/i })).toBeInTheDocument();
    expect(codeCalls).toHaveLength(0);
  });

  it('shows the code and a link to Amazon after Get my code', async () => {
    showLink(linkState());
    recordRequests('post', `${BASE}/code`, WAITING);

    render();
    await userEvent.click(await screen.findByRole('button', { name: /get my code/i }));

    expect(await screen.findByLabelText('Your code')).toHaveTextContent('AB12C');
    expect(screen.getByRole('link', { name: /open amazon.com\/code/i })).toHaveAttribute(
      'href', 'https://www.amazon.com/code',
    );
    expect(screen.getByText(/valid for 9:5\d/i)).toBeInTheDocument();
    // Copied as part of the Get my code tap, without a separate press.
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('AB12C'));
    expect(await screen.findByRole('button', { name: /copied/i })).toBeInTheDocument();
  });

  it('shows the code before the Amazon link', async () => {
    showLink(WAITING);
    render();
    const code = await screen.findByLabelText('Your code');
    const link = screen.getByRole('link', { name: /open amazon.com\/code/i });
    expect(code.compareDocumentPosition(link) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('Copy code copies, and so does opening Amazon', async () => {
    showLink(WAITING);
    render();
    await screen.findByLabelText('Your code');
    writeText.mockClear();

    await userEvent.click(screen.getByRole('button', { name: /copy code|copied/i }));
    expect(writeText).toHaveBeenLastCalledWith('AB12C');

    writeText.mockClear();
    const link = screen.getByRole('link', { name: /open amazon.com\/code/i });
    link.addEventListener('click', e => e.preventDefault()); // jsdom can't navigate
    await userEvent.click(link);
    expect(writeText).toHaveBeenLastCalledWith('AB12C');
  });

  it('a refused copy just leaves the button saying Copy code', async () => {
    writeText.mockRejectedValue(new Error('not allowed'));
    document.execCommand = vi.fn().mockReturnValue(false);
    showLink(WAITING);
    render();
    expect(await screen.findByRole('button', { name: 'Copy code' })).toBeInTheDocument();
  });

  it('falls back to execCommand when the Clipboard API is refused or missing', async () => {
    writeText.mockRejectedValue(new Error('not allowed'));
    const exec = vi.fn().mockReturnValue(true);
    document.execCommand = exec;
    showLink(WAITING);
    render();

    await userEvent.click(await screen.findByRole('button', { name: /copy code|copied/i }));

    expect(exec).toHaveBeenCalledWith('copy');
    expect(await screen.findByRole('button', { name: /copied/i })).toBeInTheDocument();

    // Plain HTTP: no navigator.clipboard at all.
    Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true });
    exec.mockClear();
    await userEvent.click(screen.getByRole('button', { name: /copied/i }));
    expect(exec).toHaveBeenCalledWith('copy');
  });

  it('starts the copy inside the Get my code tap where ClipboardItem exists', async () => {
    const write = vi.fn().mockImplementation(async (items: { data: Record<string, Promise<Blob>> }[]) => {
      await items[0].data['text/plain'];
    });
    Object.defineProperty(navigator, 'clipboard', { value: { writeText, write }, configurable: true });
    vi.stubGlobal('ClipboardItem', class { constructor(public data: Record<string, Promise<Blob>>) {} });
    showLink(linkState());
    recordRequests('post', `${BASE}/code`, WAITING);

    render();
    await userEvent.click(await screen.findByRole('button', { name: /get my code/i }));

    expect(write).toHaveBeenCalledTimes(1);
    expect(await screen.findByRole('button', { name: /copied/i })).toBeInTheDocument();
  });

  it('polls until done, then says so', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    showLink(WAITING);
    const polls = recordRequests('post', `${BASE}/poll`, linkState({ status: 'done', username: 'Pat' }));

    render();
    expect(await screen.findByLabelText('Your code')).toBeInTheDocument();
    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });

    await waitFor(() => expect(polls.length).toBeGreaterThan(0));
    expect(await screen.findByText(/all set, pat/i)).toBeInTheDocument();
  });

  it('names the account on a reconnect link', async () => {
    showLink({ ...WAITING, reauth: true, account_name: 'Christie Lyons' });

    render();

    expect(await screen.findByRole('heading', { name: /reconnect your audible account/i })).toBeInTheDocument();
    expect(screen.getByText(/\(Christie Lyons\)/)).toBeInTheDocument();
  });

  it('explains an Amazon refusal during polling and offers a new code', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let current = WAITING;
    server.use(http.get(BASE, () => HttpResponse.json(current)));
    server.use(http.post(`${BASE}/poll`, () => {
      current = linkState();
      return HttpResponse.json({ detail: 'That login belongs to a different Amazon account.' }, { status: 400 });
    }));

    render();
    await screen.findByLabelText('Your code');
    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });

    expect(await screen.findByText(/different amazon account/i)).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: /get my code/i })).toBeInTheDocument();
  });

  it('says when a code ran out', async () => {
    showLink(linkState({ code_expired: true }));
    render();
    expect(await screen.findByText(/code ran out/i)).toBeInTheDocument();
  });

  it('handles expired, used and unknown links', async () => {
    showLink(linkState({ status: 'expired' }));
    const { unmount } = render();
    expect(await screen.findByText(/link has expired/i)).toBeInTheDocument();
    unmount();

    showLink(linkState({ status: 'done', username: null }));
    const second = render();
    expect(await screen.findByText(/all set!/i)).toBeInTheDocument();
    second.unmount();

    server.use(http.get(BASE, () => HttpResponse.json({ detail: 'nope' }, { status: 404 })));
    render();
    expect(await screen.findByText(/isn’t valid/i)).toBeInTheDocument();
  });
});
