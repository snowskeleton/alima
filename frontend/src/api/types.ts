export interface User {
  id: number;
  email: string;
  role: 'admin' | 'user';
  receive_notifications?: boolean;
  created_at: string;
  last_login: string | null;
}

export interface AuthStatus {
  authenticated: boolean;
  user: User | null;
  needs_registration: boolean;
}

export interface Book {
  id: number;
  asin: string | null;
  source: 'audible' | 'imported';
  title: string;
  subtitle: string | null;
  author: string | null;
  narrator: string | null;
  series: string | null;
  series_position: string | null;
  description: string | null;
  publisher: string | null;
  publish_date: string | null;
  duration_seconds: number | null;
  genres: string[] | null;
  cover_image_path: string | null;
  cover_url: string | null;
  file_path: string | null;
  file_size: number | null;
  file_format: string | null;
  download_enabled: boolean;
  download_unavailable: boolean;
  download_error_message: string | null;
  metadata_source: 'audible' | 'file' | 'manual';
  metadata_override: Record<string, string> | null;
  added_at: string;
  downloaded_at: string | null;
  purchased_at: string | null;
  audible_account_id: number | null;
  download_queue?: DownloadQueueEntry;
}

export interface BooksResponse {
  books: Book[];
  total: number;
  offset: number;
  limit: number;
}

export interface DownloadQueueEntry {
  id: number;
  book_id: number;
  book_title: string | null;
  book_author: string | null;
  audible_account_id: number;
  account_username: string | null;
  asin: string;
  download_type: string;
  status: string;
  priority: number;
  error_message: string | null;
  attempts: number;
  file_size_bytes: number | null;
  duration_seconds: number | null;
  download_speed_kbps: number | null;
  download_quality: string | null;
  read: boolean;
  read_at: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface DownloadsResponse {
  entries: DownloadQueueEntry[];
  stats: {
    total: number;
    unread: number;
    pending: number;
    downloading: number;
    failed: number;
    completed: number;
  };
}

export interface Feed {
  id: number;
  user_id: number | null;
  name: string;
  description: string | null;
  feed_type: 'smart' | 'manual';
  filter_criteria: Record<string, unknown> | null;
  is_public: boolean;
  is_system: boolean;
  is_pinned: boolean;
  cover_image_path: string | null;
  slug: string;
  created_at: string;
  updated_at: string;
  rss_url: string | null;
  books?: Book[];
}

export interface AudibleAccount {
  id: number;
  username: string;
  marketplace: string;
  enabled: boolean;
  downloads_enabled: boolean;
  last_sync_timestamp: string | null;
  added_at: string;
}

export interface BackgroundJob {
  id: number;
  job_type: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  progress: number;
  total: number;
  result: unknown;
  error_message: string | null;
  meta: Record<string, unknown> | null;
  created_at: string;
  completed_at: string | null;
}

export interface AuditResult {
  book_title: string;
  book_author: string;
  file_title: string | null;
  file_author: string | null;
  title_score: number;
  author_score: number;
  file_path: string;
  status: 'good' | 'warning' | 'bad' | 'missing';
}

export interface ApiKey {
  id: number;
  name: string;
  key_prefix: string;
  created_at: string;
}
