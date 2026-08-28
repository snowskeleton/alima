import { fireEvent, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { makeBook } from '../../test/handlers';
import { currentPath, renderWithProviders } from '../../test/utils';
import type { Book } from '../../api/types';
import { BookCard } from './BookCard';

function book(overrides: Record<string, unknown> = {}) {
  return makeBook(overrides) as unknown as Book;
}

describe('BookCard', () => {
  describe('status badge', () => {
    const cases: [string, Record<string, unknown>, RegExp][] = [
      ['downloaded', { file_path: '/audiobooks/hobbit.m4b' }, /downloaded/i],
      ['unavailable', { download_unavailable: true }, /unavailable/i],
      ['auto-download off', { download_enabled: false }, /disabled/i],
      ['waiting', {}, /pending/i],
    ];

    it.each(cases)('reads %s', (_label, overrides, expected) => {
      renderWithProviders(<BookCard book={book(overrides)} />);

      expect(screen.getByText(expected)).toBeInTheDocument();
    });

    it('prefers "downloaded" over every other state', () => {
      // A book on disk that is also flagged unavailable is downloaded as far
      // as the user is concerned; showing "unavailable" would be a lie.
      renderWithProviders(
        <BookCard book={book({ file_path: '/x.m4b', download_unavailable: true })} />,
      );

      expect(screen.getByText(/downloaded/i)).toBeInTheDocument();
      expect(screen.queryByText(/unavailable/i)).toBeNull();
    });
  });

  it('links to the book in every view', () => {
    for (const view of ['grid', 'list', 'compact'] as const) {
      const { unmount } = renderWithProviders(
        <BookCard book={book({ id: 7 })} view={view} />,
      );
      expect(screen.getByRole('link')).toHaveAttribute('href', '/library/7');
      unmount();
    }
  });

  it('uses the stored cover in preference to the remote one', () => {
    // The remote URL expires; the stored file does not.
    const { container } = renderWithProviders(
      <BookCard
        book={book({ cover_image_path: 'covers/7.jpg', cover_url: 'https://audible/x.jpg' })}
      />,
    );

    expect(container.querySelector('img')).toHaveAttribute('src', '/files/covers/7.jpg');
  });

  it('falls back to the remote cover when nothing is stored', () => {
    const { container } = renderWithProviders(
      <BookCard book={book({ cover_image_path: null, cover_url: 'https://audible/x.jpg' })} />,
    );

    expect(container.querySelector('img')).toHaveAttribute('src', 'https://audible/x.jpg');
  });

  it('says so rather than showing a broken image when there is no cover', () => {
    renderWithProviders(
      <BookCard book={book({ cover_image_path: null, cover_url: null })} />,
    );

    expect(screen.getByText(/no cover/i)).toBeInTheDocument();
  });

  it('reports a right-click to its parent, with the book it happened on', () => {
    const onContextMenu = vi.fn();
    renderWithProviders(
      <BookCard book={book({ id: 7 })} onContextMenu={onContextMenu} />,
    );

    fireEvent.contextMenu(screen.getByText('The Hobbit'));

    expect(onContextMenu).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({ id: 7 }));
  });

  describe('selectable compact view', () => {
    it('selects on the checkbox rather than navigating', async () => {
      const onSelect = vi.fn();
      renderWithProviders(
        <BookCard book={book({ id: 7 })} view="compact" onSelect={onSelect} />,
        { route: '/library', path: '/library' },
      );

      await userEvent.click(screen.getByRole('checkbox'));

      expect(onSelect).toHaveBeenCalledWith(7, false);
      expect(currentPath()).toBe('/library');
    });

    it('passes the shift key through, so range selection can work', async () => {
      const onSelect = vi.fn();
      renderWithProviders(
        <BookCard book={book({ id: 7 })} view="compact" onSelect={onSelect} />,
      );

      fireEvent.click(screen.getByRole('checkbox'), { shiftKey: true });

      expect(onSelect).toHaveBeenCalledWith(7, true);
    });

    it('navigates when the row itself is clicked', async () => {
      const onSelect = vi.fn();
      renderWithProviders(
        <BookCard book={book({ id: 7 })} view="compact" onSelect={onSelect} />,
        { route: '/library', path: '/library' },
      );

      await userEvent.click(screen.getByText('The Hobbit'));

      expect(onSelect).not.toHaveBeenCalled();
      expect(currentPath()).toBe('/library/7');
    });

    it('reflects the selected state it was given', () => {
      renderWithProviders(
        <BookCard book={book()} view="compact" selected onSelect={vi.fn()} />,
      );

      expect(screen.getByRole('checkbox')).toBeChecked();
    });
  });
});
