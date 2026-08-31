import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { expect, type Page } from '@playwright/test';

const ROOT = path.resolve(__dirname, '..');
const DB_PATH = path.join(ROOT, '.e2e', 'e2e.db');

/**
 * Read the most recent magic-link token for an address straight out of the
 * database.
 *
 * The alternative -- a test-only endpoint that hands back the newest token --
 * would put a credential-disclosure route in the real application, one
 * misconfiguration away from being a full authentication bypass. Reading the
 * row directly keeps that surface out of the app entirely; the cost is that
 * this helper knows the schema, which a schema change will break loudly.
 */
export function latestMagicLinkToken(email: string): string {
  const output = execFileSync(
    'sqlite3',
    [
      DB_PATH,
      `SELECT token FROM magic_links WHERE email = '${email.replace(/'/g, "''")}' ` +
        `ORDER BY id DESC LIMIT 1;`,
    ],
    { encoding: 'utf8' },
  ).trim();

  if (!output) {
    throw new Error(
      `No magic link found for ${email}. The login request either failed or ` +
        `never reached the database.`,
    );
  }
  return output;
}

/** Count rows, for assertions about what the API actually persisted. */
export function countRows(table: string): number {
  return Number(
    execFileSync('sqlite3', [DB_PATH, `SELECT COUNT(*) FROM ${table};`], {
      encoding: 'utf8',
    }).trim(),
  );
}

/**
 * Register the first user. Only works on a fresh database, which is exactly
 * what scripts/e2e-server.sh guarantees on every start.
 */
export async function registerFirstUser(page: Page, email: string) {
  await page.goto('/auth/register');
  await page.getByLabel(/email/i).fill(email);
  await page.getByRole('button', { name: /register|create|sign up/i }).click();
}

/** Complete a magic-link login for an existing user. */
export async function loginAs(page: Page, email: string) {
  await page.goto('/auth/login');
  await page.getByLabel(/email/i).fill(email);
  await page.getByRole('button', { name: /magic link/i }).click();

  // The page confirms the link was sent before the row is guaranteed written.
  await expect(page).toHaveURL(/magic-link-sent/);

  const token = latestMagicLinkToken(email);
  await page.goto(`/auth/magic-link?token=${token}`);
  await expect(page).toHaveURL(/library|feeds|\/$/);
}
