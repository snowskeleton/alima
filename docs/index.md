# Alima 2.0 Documentation

Welcome to Alima 2.0 - your personal audiobook library manager for Audible.

## What is Alima?

Alima is a self-hosted audiobook library manager that:

- **Downloads your Audible library** - Keep local copies with parallel downloads
- **Import existing audiobooks** - Match and organize your existing files
- **Creates RSS feeds** - Listen in your favorite podcast app
- **Manages multiple accounts** - Support for multiple Audible accounts
- **Auto-syncs** - Keeps your library up to date automatically
- **Docker ready** - Easy deployment with Docker Compose
- **Secure** - Encrypted credential storage and invite-only registration

## Quick Links

- [Installation Guide](getting-started/installation.md) - Get started in 5 minutes
- [User Guide](user-guide/audible-accounts.md) - Learn how to use Alima
- [API Reference](api/models.md) - Code documentation
- [GitHub Repository](https://github.com/yourusername/alima2.0) - Source code

## Features

### 📚 Library Management
Browse, search, and organize your audiobook collection with automatic metadata and cover art. Import existing audiobook files with intelligent fuzzy matching.

### 🔄 Automatic Syncing
Connects to Audible and automatically syncs your library every 6 hours (configurable). Downloads up to 3 books in parallel for faster processing.

### 📡 RSS Feeds
Create personal RSS feeds to listen to your audiobooks in any podcast app.

### 👥 Multi-User Support
Invite-based user system with role-based access control (admin/user).

### 🔐 Security First
- Encrypted credential storage
- Session-based authentication
- CSRF protection
- Invite-only registration

### ⚙️ Easy Configuration
Web-based settings page - no need to edit config files or restart the server.

## Architecture

Alima is built with modern Python tools:

- **FastAPI** - High-performance async web framework
- **SQLAlchemy 2.0** - Modern ORM with type safety
- **Jinja2** - Server-side templating
- **APScheduler** - Background sync jobs
- **Audible API** - Official Audible integration

## Getting Started

1. [Install Alima](getting-started/installation.md)
2. [Configure your settings](getting-started/configuration.md)
3. [Add your first Audible account](user-guide/audible-accounts.md)
4. [Create an RSS feed](user-guide/rss-feeds.md)

## Support

- **GitHub Issues** - Bug reports and feature requests
- **Documentation** - You're reading it!

## License

MIT License - See LICENSE file for details
