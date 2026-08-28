import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '../../test/utils';
import {
  FeedFilterEditor,
  parseFilterCriteria,
  serializeFilters,
  type FeedFilter,
} from './FeedFilterEditor';

describe('parseFilterCriteria', () => {
  it('reads the current multi-filter format', () => {
    expect(
      parseFilterCriteria({
        filters: [{ field: 'author', operator: 'is', value: 'Tolkien' }],
      }),
    ).toEqual([{ field: 'author', operator: 'is', value: 'Tolkien' }]);
  });

  it('reads the legacy single-filter format the backend still accepts', () => {
    // Feeds created before the multi-filter editor store {type, value}; losing
    // them here would silently widen the feed to the whole library.
    expect(parseFilterCriteria({ type: 'series', value: 'Mistborn' })).toEqual([
      { field: 'series', operator: 'contains', value: 'Mistborn' },
    ]);
  });

  it('maps a legacy `type` key inside the filters array to `field`', () => {
    expect(parseFilterCriteria({ filters: [{ type: 'narrator', value: 'Inglis' }] })).toEqual([
      { field: 'narrator', operator: 'contains', value: 'Inglis' },
    ]);
  });

  it('defaults a missing operator to contains', () => {
    expect(parseFilterCriteria({ filters: [{ field: 'title', value: 'Dune' }] })).toEqual([
      { field: 'title', operator: 'contains', value: 'Dune' },
    ]);
  });

  it('drops rows with no value, which would match everything', () => {
    expect(
      parseFilterCriteria({ filters: [{ field: 'author', value: '' }] }),
    ).toEqual([]);
  });

  it('returns nothing for null, undefined, or an unrecognised shape', () => {
    expect(parseFilterCriteria(null)).toEqual([]);
    expect(parseFilterCriteria(undefined)).toEqual([]);
    expect(parseFilterCriteria({ nonsense: true })).toEqual([]);
  });
});

describe('serializeFilters', () => {
  it('trims values so a stray space does not become part of the match', () => {
    expect(JSON.parse(serializeFilters([
      { field: 'author', operator: 'is', value: '  Tolkien  ' },
    ]))).toEqual([{ field: 'author', operator: 'is', value: 'Tolkien' }]);
  });

  it('drops rows the user left blank', () => {
    expect(JSON.parse(serializeFilters([
      { field: 'author', operator: 'contains', value: 'Tolkien' },
      { field: 'title', operator: 'contains', value: '   ' },
    ]))).toEqual([{ field: 'author', operator: 'contains', value: 'Tolkien' }]);
  });

  it('serialises an empty editor as an empty list, not null', () => {
    expect(serializeFilters([])).toBe('[]');
  });
});

describe('FeedFilterEditor', () => {
  function setup(filters: FeedFilter[] = []) {
    const onChange = vi.fn();
    renderWithProviders(<FeedFilterEditor filters={filters} onChange={onChange} />);
    return onChange;
  }

  it('Add Filter appends a row with sensible defaults', async () => {
    const onChange = setup([]);

    await userEvent.click(screen.getByRole('button', { name: /add filter/i }));

    expect(onChange).toHaveBeenCalledWith([
      { field: 'author', operator: 'contains', value: '' },
    ]);
  });

  it('Remove drops only the row it belongs to', async () => {
    const onChange = setup([
      { field: 'author', operator: 'contains', value: 'Tolkien' },
      { field: 'title', operator: 'contains', value: 'Hobbit' },
    ]);

    await userEvent.click(screen.getAllByRole('button', { name: /remove/i })[0]);

    expect(onChange).toHaveBeenCalledWith([
      { field: 'title', operator: 'contains', value: 'Hobbit' },
    ]);
  });

  it('editing one row leaves the others alone', async () => {
    const onChange = setup([
      { field: 'author', operator: 'contains', value: 'Tolkien' },
      { field: 'title', operator: 'contains', value: 'Hobbit' },
    ]);

    await userEvent.selectOptions(screen.getAllByLabelText('Operator')[1], 'is_not');

    expect(onChange).toHaveBeenCalledWith([
      { field: 'author', operator: 'contains', value: 'Tolkien' },
      { field: 'title', operator: 'is_not', value: 'Hobbit' },
    ]);
  });

  it('changes the field of the row that was edited', async () => {
    const onChange = setup([{ field: 'author', operator: 'contains', value: 'Tolkien' }]);

    await userEvent.selectOptions(screen.getByLabelText('Field'), 'narrator');

    expect(onChange).toHaveBeenCalledWith([
      { field: 'narrator', operator: 'contains', value: 'Tolkien' },
    ]);
  });
});
