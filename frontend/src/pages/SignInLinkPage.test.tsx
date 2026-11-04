import { act, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { afterEach, describe, expect, it, vi } from 'vitest';
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

afterEach(() => vi.useRealTimers());

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
