export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

function getCsrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)alima_csrf=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : '';
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers: Record<string, string> = {
    'x-csrf-token': getCsrfToken(),
    ...(options.headers as Record<string, string> || {}),
  };

  // Only set Content-Type for non-FormData bodies
  if (!(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }

  const response = await fetch(`/api/v2${path}`, {
    ...options,
    credentials: 'same-origin',
    headers,
  });

  if (response.status === 401) {
    window.location.href = '/auth/login';
    throw new ApiError(401, 'Unauthorized');
  }

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(response.status, body.detail || 'Request failed');
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}
