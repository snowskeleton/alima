export function getCsrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)alima_csrf=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : '';
}
