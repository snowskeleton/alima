import { Routes, Route, Navigate } from 'react-router-dom';
import { AppShell } from './components/layout/AppShell';
import { ProtectedRoute } from './components/layout/ProtectedRoute';
import { AdminRoute } from './components/layout/AdminRoute';

import { LoginPage } from './pages/LoginPage';
import { RegisterPage } from './pages/RegisterPage';
import { MagicLinkSentPage } from './pages/MagicLinkSentPage';
import { MagicLinkCallbackPage } from './pages/MagicLinkCallbackPage';
import { ProfilePage } from './pages/ProfilePage';
import { LibraryPage } from './pages/LibraryPage';
import { BookDetailPage } from './pages/BookDetailPage';
import { BookEditPage } from './pages/BookEditPage';
import { FeedListPage } from './pages/FeedListPage';
import { FeedCreatePage } from './pages/FeedCreatePage';
import { FeedEditPage } from './pages/FeedEditPage';
import { FeedDetailPage } from './pages/FeedDetailPage';
import { AccountListPage } from './pages/AccountListPage';
import { AccountLoginPage } from './pages/AccountLoginPage';
import { DownloadQueuePage } from './pages/DownloadQueuePage';
import { UserListPage } from './pages/UserListPage';
import { ApiKeyPage } from './pages/ApiKeyPage';
import { SettingsPage } from './pages/SettingsPage';
import { LogsPage } from './pages/LogsPage';
import { AuditPage } from './pages/AuditPage';
import { MatchBooksPage } from './pages/MatchBooksPage';
import { ImportPage } from './pages/ImportPage';

export default function App() {
  return (
    <Routes>
      {/* Auth routes (no shell) */}
      <Route path="/auth/login" element={<LoginPage />} />
      <Route path="/auth/register" element={<RegisterPage />} />
      <Route path="/auth/magic-link-sent" element={<MagicLinkSentPage />} />
      <Route path="/auth/magic-link" element={<MagicLinkCallbackPage />} />

      {/* Public routes with shell — anonymous visitors must reach these.
          The server decides what's visible: /feeds/by-slug/{slug} 403s on a
          private feed, so the guard here would only ever be redundant. */}
      <Route element={<AppShell />}>
        <Route path="/feed/:slug" element={<FeedDetailPage />} />
      </Route>

      {/* Authenticated routes with shell */}
      <Route element={<ProtectedRoute />}>
        <Route element={<AppShell />}>
          <Route path="/auth/profile" element={<ProfilePage />} />
          <Route path="/library" element={<LibraryPage />} />
          <Route path="/library/:bookId" element={<BookDetailPage />} />

          {/* Feeds */}
          <Route path="/feeds" element={<FeedListPage />} />
          <Route path="/feeds/create" element={<FeedCreatePage />} />
          <Route path="/feeds/:feedId/edit" element={<FeedEditPage />} />

          {/* Admin routes */}
          <Route element={<AdminRoute />}>
            <Route path="/books/:bookId/edit" element={<BookEditPage />} />
            <Route path="/admin/accounts" element={<AccountListPage />} />
            <Route path="/admin/accounts/login" element={<AccountLoginPage />} />
            <Route path="/admin/downloads" element={<DownloadQueuePage />} />
            <Route path="/admin/users" element={<UserListPage />} />
            <Route path="/admin/api-keys" element={<ApiKeyPage />} />
            <Route path="/admin/settings" element={<SettingsPage />} />
            <Route path="/admin/import" element={<ImportPage />} />
            <Route path="/admin/match-books" element={<MatchBooksPage />} />
            <Route path="/admin/audit" element={<AuditPage />} />
            <Route path="/logs" element={<LogsPage />} />
          </Route>
        </Route>
      </Route>

      {/* Default redirect. Must be a real redirect, not a bare <LibraryPage />:
          rendering it directly bypasses ProtectedRoute and AppShell, so an
          unknown URL showed anonymous visitors a chrome-less page of failed
          requests instead of sending them to login. */}
      <Route path="*" element={<Navigate to="/library" replace />} />
    </Routes>
  );
}
