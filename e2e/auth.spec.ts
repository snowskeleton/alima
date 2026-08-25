import { expect, test } from '@playwright/test';
import { countRows, latestMagicLinkToken } from './helpers';

/**
 * The first-run and login flows.
 *
 * These run first and in order: the database starts empty on every server
 * start, so registration must claim the first-user slot before anything else
 * needs a session.
 */

const ADMIN = 'e2e-admin@example.com';

test.describe.configure({ mode: 'serial' });

test('an empty instance sends visitors to registration', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveURL(/\/auth\/register/);
});

test('the first user registers and becomes an admin', async ({ page }) => {
  await page.goto('/auth/register');
  await page.getByLabel(/email/i).fill(ADMIN);
  await page.getByRole('button', { name: /create admin account/i }).click();

  await expect(page).toHaveURL(/library|feeds|magic-link/, { timeout: 15_000 });
  expect(countRows('users')).toBe(1);
});

test('registration is closed once a user exists', async ({ page }) => {
  // Otherwise anyone reaching /auth/register on a live instance could claim a
  // second admin account.
  await page.goto('/auth/register');
  await expect(page).toHaveURL(/\/auth\/login/, { timeout: 15_000 });
});

test('a magic link signs an existing user in', async ({ page }) => {
  await page.context().clearCookies();

  await page.goto('/auth/login');
  await page.getByLabel(/email/i).fill(ADMIN);
  await page.getByRole('button', { name: /magic link/i }).click();
  await expect(page).toHaveURL(/magic-link-sent/);

  const token = latestMagicLinkToken(ADMIN);
  await page.goto(`/auth/magic-link?token=${token}`);

  await expect(page).toHaveURL(/library|feeds/, { timeout: 15_000 });
});

test('a magic link cannot be replayed', async ({ page }) => {
  // The token is single-use. If a used link still worked, a leaked email or a
  // shared browser history would be a standing way in.
  await page.context().clearCookies();

  await page.goto('/auth/login');
  await page.getByLabel(/email/i).fill(ADMIN);
  await page.getByRole('button', { name: /magic link/i }).click();
  await expect(page).toHaveURL(/magic-link-sent/);

  const token = latestMagicLinkToken(ADMIN);
  await page.goto(`/auth/magic-link?token=${token}`);
  await expect(page).toHaveURL(/library|feeds/, { timeout: 15_000 });

  await page.context().clearCookies();
  await page.goto(`/auth/magic-link?token=${token}`);
  await expect(page).not.toHaveURL(/library|feeds/);
});

test('a forged token is rejected', async ({ page }) => {
  await page.context().clearCookies();
  await page.goto('/auth/magic-link?token=definitely-not-a-real-token');
  await expect(page).not.toHaveURL(/library|feeds/);
});

test('signed-out visitors cannot reach the library', async ({ page }) => {
  await page.context().clearCookies();
  await page.goto('/library');
  await expect(page).toHaveURL(/\/auth\/login/, { timeout: 15_000 });
});
