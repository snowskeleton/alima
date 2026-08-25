import { describe, expect, it, vi } from 'vitest';
import { formatDuration, formatFileSize, timeAgo } from './format';

/**
 * These run on every row of the library grid and the download queue, so a
 * wrong answer here is the most visible kind of bug in the app.
 */

describe('formatDuration', () => {
  it.each([
    [null, ''],
    [0, ''],
    [59, '0m'],
    [60, '1m'],
    [3599, '59m'],
    [3600, '1h 0m'],
    [39600, '11h 0m'],
    [3661, '1h 1m'],
  ])('formats %s as %s', (input, expected) => {
    expect(formatDuration(input as number | null)).toBe(expected);
  });

  it('does not render a bare hour count without minutes', () => {
    // "11h" alone reads as an estimate; the grid column is fixed width and
    // expects both parts.
    expect(formatDuration(39600)).toMatch(/^\d+h \d+m$/);
  });
});

describe('formatFileSize', () => {
  it.each([
    [null, ''],
    [0, ''],
    [512, '512 B'],
    [1024, '1.0 KB'],
    [1536, '1.5 KB'],
    [1024 * 1024, '1.0 MB'],
    [1024 * 1024 * 1024, '1.00 GB'],
  ])('formats %s as %s', (input, expected) => {
    expect(formatFileSize(input as number | null)).toBe(expected);
  });

  it('switches unit exactly at the boundary, not one byte early', () => {
    expect(formatFileSize(1023)).toBe('1023 B');
    expect(formatFileSize(1024)).toBe('1.0 KB');
  });

  it('gives gigabytes an extra digit', () => {
    // Audiobooks cluster between 1 and 3 GB, so one decimal would make most of
    // the library look like the same size.
    expect(formatFileSize(2.75 * 1024 ** 3)).toBe('2.75 GB');
  });
});

describe('timeAgo', () => {
  const now = new Date('2024-06-15T12:00:00Z');

  function ago(ms: number) {
    vi.setSystemTime(now);
    return timeAgo(new Date(now.getTime() - ms).toISOString());
  }

  it('reports never for a missing timestamp', () => {
    expect(timeAgo(null)).toBe('never');
  });

  it.each([
    [30_000, 'just now'],
    [60_000, '1m ago'],
    [59 * 60_000, '59m ago'],
    [60 * 60_000, '1h ago'],
    [23 * 3600_000, '23h ago'],
    [24 * 3600_000, '1d ago'],
    [29 * 24 * 3600_000, '29d ago'],
  ])('renders %sms ago as %s', (ms, expected) => {
    vi.useFakeTimers();
    expect(ago(ms as number)).toBe(expected);
    vi.useRealTimers();
  });

  it('falls back to a date past 30 days', () => {
    vi.useFakeTimers();
    const result = ago(60 * 24 * 3600_000);
    vi.useRealTimers();
    expect(result).not.toMatch(/ago$/);
  });
});
