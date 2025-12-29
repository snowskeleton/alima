# API Routers

Auto-generated documentation for Alima's API endpoints.

## Overview

Alima's API is organized into routers by functionality. Most endpoints return HTML pages (using Jinja2 templates), while some return JSON for AJAX requests.

## Authentication

::: app.routers.auth
    options:
      show_source: false
      heading_level: 3

Handles user authentication:

- `GET /auth/login` - Login page
- `POST /auth/login` - Process login
- `GET /auth/register` - Registration page (first user only)
- `POST /auth/register` - Create account
- `POST /auth/logout` - Logout
- `GET /auth/accept-invite` - Accept invitation

## Admin Routes

::: app.routers.admin
    options:
      show_source: false
      heading_level: 3

Admin-only functionality:

- `GET /admin/users` - User management page
- `POST /admin/invites/send` - Send invitation
- `POST /admin/invites/{invite_id}/revoke` - Revoke invitation
- `POST /admin/users/{user_id}/role` - Change user role
- `DELETE /admin/users/{user_id}` - Delete user

## Audible Accounts

::: app.routers.accounts
    options:
      show_source: false
      heading_level: 3

Audible account management:

- `GET /admin/accounts` - List accounts
- `POST /admin/accounts/add` - Add account
- `POST /admin/accounts/{id}/sync` - Trigger sync
- `DELETE /admin/accounts/{id}` - Remove account

## Library

::: app.routers.library
    options:
      show_source: false
      heading_level: 3

Browse and search audiobooks:

- `GET /library` - Library page
- `GET /library/search` - Search results

## Books

::: app.routers.books
    options:
      show_source: false
      heading_level: 3

Individual book operations:

- `GET /books/{id}` - Book details
- `POST /books/{id}/download` - Download book
- `DELETE /books/{id}` - Delete book

## RSS Feeds

::: app.routers.feeds
    options:
      show_source: false
      heading_level: 3

Feed management:

- `GET /feeds` - List feeds
- `POST /feeds/create` - Create feed
- `PUT /feeds/{id}` - Update feed
- `DELETE /feeds/{id}` - Delete feed

## RSS Generation

::: app.routers.rss
    options:
      show_source: false
      heading_level: 3

RSS feed XML generation:

- `GET /rss/{feed_id}` - Generate RSS XML

## Server Settings

::: app.routers.settings
    options:
      show_source: false
      heading_level: 3

Server configuration:

- `GET /admin/settings` - Settings page
- `POST /admin/settings/update` - Save settings
- `POST /admin/settings/test-email` - Test email configuration

## File Serving

::: app.routers.files
    options:
      show_source: false
      heading_level: 3

Static file serving:

- `GET /files/covers/{filename}` - Serve cover images
- `GET /files/audiobooks/{filename}` - Serve audiobook files

## Built-in API Documentation

FastAPI provides interactive API documentation:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

These are automatically generated from the code and allow you to test endpoints directly in the browser.
