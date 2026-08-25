import { expect, test } from '@playwright/test';
import { countRows, loginAs } from './helpers';

/**
 * Feed creation through to a podcast client fetching the RSS.
 *
 * This is the app's actual purpose, and the one flow that spans the browser,
 * the API, the feed generator, and the public RSS route. Nothing below the E2E
 * layer covers all four together.
 */

const ADMIN = 'e2e-admin@example.com';

test.describe.configure({ mode: 'serial' });

test.beforeEach(async ({ page }) => {
  await loginAs(page, ADMIN);
});

test('a feed can be created from the UI', async ({ page }) => {
  const before = countRows('feeds');

  await page.goto('/feeds/create');
  await page.getByLabel(/name/i).first().fill('E2E Test Feed');
  await page.getByRole('button', { name: /create|save/i }).first().click();

  await expect(page).toHaveURL(/\/feeds/, { timeout: 15_000 });
  expect(countRows('feeds')).toBe(before + 1);
});

test('the new feed appears in the list', async ({ page }) => {
  await page.goto('/feeds');
  await expect(page.getByText('E2E Test Feed')).toBeVisible({ timeout: 15_000 });
});

/**
 * Helper: talk to the API with the browser's own session.
 *
 * Feed state is manipulated through the API rather than by clicking, because
 * what these two tests are actually about is the public RSS contract, not the
 * settings form. Scraping ids and slugs out of the DOM made them fail whenever
 * the list markup changed, which is noise rather than signal.
 */
async function apiContext(page: import('@playwright/test').Page) {
  const cookies = await page.context().cookies();
  return {
    cookie: cookies.map((c) => `${c.name}=${c.value}`).join('; '),
    csrf: cookies.find((c) => c.name === 'alima_csrf')?.value ?? '',
  };
}

async function findFeed(page: import('@playwright/test').Page, request: any, name: string) {
  const { cookie } = await apiContext(page);
  const response = await request.get('/api/v2/feeds', { headers: { cookie } });
  expect(response.ok()).toBeTruthy();
  const feed = (await response.json()).feeds.find((f: any) => f.name === name);
  expect(feed, `no feed named ${name}`).toBeTruthy();
  return feed;
}

async function setFeedPublic(
  page: import('@playwright/test').Page,
  request: any,
  feed: any,
  isPublic: boolean,
) {
  const { cookie, csrf } = await apiContext(page);
  const response = await request.put(`/api/v2/feeds/${feed.id}`, {
    headers: {
      cookie,
      'x-csrf-token': csrf,
      'content-type': 'application/x-www-form-urlencoded',
    },
    data: new URLSearchParams({
      name: feed.name,
      is_public: String(isPublic),
    }).toString(),
  });
  expect(response.ok()).toBeTruthy();
  return response.json();
}

test('a private feed does not serve RSS to anonymous clients', async ({ page, request }) => {
  // Feeds default to private and the RSS route is public, so this is the check
  // that stops a private library leaking to anyone who learns the slug.
  const feed = await findFeed(page, request, 'E2E Test Feed');
  await setFeedPublic(page, request, feed, false);

  const rss = await request.get(`/feed/${feed.slug}.xml`);
  expect([403, 404]).toContain(rss.status());
});

test('the RSS route returns XML for a public feed', async ({ page, request }) => {
  const feed = await findFeed(page, request, 'E2E Test Feed');
  const updated = await setFeedPublic(page, request, feed, true);

  // Fetched the way a podcast player would: no session, no headers.
  const rss = await request.get(`/feed/${updated.slug}.xml`);

  expect(rss.status()).toBe(200);
  expect(rss.headers()['content-type']).toContain('xml');

  const body = await rss.text();
  expect(body).toContain('<rss');
  expect(body).toContain('E2E Test Feed');
});
