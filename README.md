# Alima 2.0

Audiobook library manager for Audible - Download, organize, and share your audiobooks with RSS feeds.

## Quick Start

Choose your preferred installation method:

- **[Docker](#docker-quick-start)** - Recommended for production
- **[Manual](#manual-installation)** - For development

## Docker Quick Start

The easiest way to run Alima:

```bash
# 1. Copy environment template
cp .env.docker .env

# 2. Edit .env and set SECRET_KEY
# Generate with: openssl rand -hex 32
vi .env

# 3. Create data directories
mkdir -p data/{audiobooks/unassigned,covers,audible_auth,temp,db}

# 4. Start the container
docker compose up -d

# 5. Access at http://localhost:8000
```

See [DOCKER_SETUP.md](DOCKER_SETUP.md) for complete Docker documentation.

## Manual Installation

### 1. Install Dependencies

```bash
# Activate virtual environment
source .venv/bin/activate

# Install requirements
pip install -r requirements.txt

# Install frontend dependencies
cd frontend && npm install && cd ..
```

### 2. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env and set at minimum:
# - SECRET_KEY (generate with: openssl rand -hex 32)
nano .env
```

### 3. Build the Frontend

```bash
cd frontend && npm run build && cd ..
```

This builds the React SPA into `app/static/spa/`, which FastAPI serves automatically.

### 4. Run the Application

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The app will be available at: http://localhost:8000

**First time setup:** The database and data directories will be created automatically on first run.

## Development

### Running in Development Mode

Development requires two processes: the backend server and a frontend watcher that rebuilds on file changes.

```bash
# Terminal 1: frontend watcher (rebuilds on save)
cd frontend && npm run watch

# Terminal 2: backend server (auto-restarts on Python changes)
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

After saving a frontend file, Vite rebuilds automatically (~1s). Refresh the browser to see changes. The backend's `--reload` flag auto-restarts on Python file changes.

**Note**: The `.env` file is configured for local development with SQLite. To test with Docker (which uses PostgreSQL), use `docker compose --env-file .env.docker up --build`.

### Running Tests

```bash
source .venv/bin/activate
pytest -v                    # Verbose output
pytest tests/test_auth.py    # Run specific test file
pytest -k "test_login"       # Run tests matching pattern
```

**Note**: Tests never send real emails. All email functionality is automatically mocked to protect your domain reputation.

### Code Style

The project uses:
- Type hints throughout
- SQLAlchemy 2.0 style with `Mapped` types
- Async/await for I/O operations
- Pydantic for configuration and validation

## Architecture

```
alima2.0/
├── app/
│   ├── main.py              # FastAPI application entry point
│   ├── config.py            # Configuration management
│   ├── database.py          # Database setup and session management
│   ├── models.py            # SQLAlchemy database models
│   ├── dependencies.py      # FastAPI dependencies (auth, etc.)
│   ├── routers/
│   │   ├── api_v2/          # JSON API consumed by the React SPA
│   │   ├── files.py         # Audiobook/cover file serving
│   │   ├── rss.py           # RSS feed generation (XML)
│   │   ├── api.py           # SSE real-time status endpoints
│   │   └── ext_api.py       # External v1 API for integrations
│   ├── services/            # Business logic services
│   │   ├── audible_service.py      # Audible API integration
│   │   ├── email_service.py        # Email sending
│   │   ├── settings_service.py     # Settings with encryption
│   │   └── snowcrypt_service.py    # Encryption for Audible auth
│   ├── workers/             # Background tasks
│   │   └── scheduler.py     # Scheduled sync jobs
│   └── static/              # Static assets
│       └── spa/             # Built React SPA (generated, not in git)
├── frontend/                # React SPA source
│   ├── src/
│   │   ├── pages/           # Page components
│   │   ├── components/      # Reusable UI components
│   │   ├── api/             # API client, hooks, types
│   │   └── App.tsx          # Router and layout
│   ├── package.json
│   └── vite.config.ts       # Vite build config
├── tests/                   # Test suite
├── data/                    # Data directory (created on first run)
│   ├── db/                  # SQLite database
│   ├── audiobooks/          # Downloaded audiobook files
│   │   └── unassigned/      # Place files here to match to books
│   ├── covers/              # Cover images
│   ├── audible_auth/        # Audible authentication files
│   └── temp/                # Temporary files
├── .env                     # Environment configuration (not in git)
├── .env.example             # Example environment file
├── requirements.txt         # Python dependencies
└── README.md
```

## Configuration

Edit `.env` file to configure:

### Required Settings

- `SECRET_KEY` - Random secret key for sessions (generate with `openssl rand -hex 32`)
- `DOMAIN` - Full URL where the app is hosted
  - Development: `http://localhost:8000`
  - Production (with SSL): `https://alima.example.com`
  - **Important**: Set to `https://` if using SSL - this tells FastAPI to generate HTTPS URLs

### Optional Settings

- **Email (SMTP)** - Can also be configured via web UI at `/admin/settings`
  - `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`

- **Paths** - Data storage locations
  - `AUDIOBOOKS_PATH` - Where audiobook files are stored
  - `COVERS_PATH` - Where cover images are stored
  - `AUDIBLE_AUTH_PATH` - Where Audible authentication files are stored
  - `TEMP_PATH` - Temporary file storage

- **Database**
  - `DATABASE_URL` - Database connection string (default: `sqlite:///data/db/alima.db`)

- **Sync** - Can also be configured via web UI
  - `SYNC_INTERVAL_HOURS` - How often to sync with Audible (default: 6)
  - `DOWNLOAD_QUALITY` - Audio quality: `High` or `Normal` (default: `High`)
  - `MAX_CONCURRENT_DOWNLOADS` - Number of parallel downloads (default: 3)

- **Session** - Can also be configured via web UI
  - `SESSION_EXPIRE_HOURS` - How long sessions last (default: 168 = 7 days)
  - `INVITE_EXPIRE_DAYS` - How long invite links are valid (default: 7)

**Note**: Settings for sync intervals, download quality, and session expiration can be changed via the web UI at `/admin/settings` without editing files or restarting the server.

## Features

### User Management
- Admin user management at `/admin/users`
- Invite-based registration system
- Role-based access control (admin/user)

### Audible Integration
- Multiple Audible account support
- Automatic library syncing (every 6 hours by default)
- External browser authentication flow
- Encrypted credential storage

### Audiobook Library
- Browse and search your audiobooks
- Right-click context menu for quick actions on any book
- Bulk selection and actions in compact view
- Automatic metadata and cover download
- Parallel downloads (configurable concurrency)
- Book matching - import existing audiobook files

### RSS Feeds
- Create personal RSS feeds for podcast apps
- Share feeds with other users
- Automatic feed updates

### Server Settings
- Web-based configuration at `/admin/settings`
- Encrypted storage for sensitive data (SMTP passwords, etc.)
- No need to edit config files or restart after changes

## Troubleshooting

### "Module not found" errors
Make sure the virtual environment is activated:
```bash
source .venv/bin/activate
```

### Frontend not loading / 503 error
Build the frontend first:
```bash
cd frontend && npm run build
```

### Database errors
The database is automatically created on first run. If you have issues:
```bash
# Delete the database and let it recreate
rm -rf data/db/
# Restart the app
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Port already in use
If port 8000 is already taken, use a different port:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

### Can't access from other devices
Make sure you're binding to `0.0.0.0` (not `127.0.0.1`) and update `DOMAIN` in `.env`:
```bash
# In .env:
DOMAIN=http://your-ip-address:8000
```

### CSS/Images not loading behind reverse proxy
If running behind Caddy/Nginx and CSS or images don't load:

1. **Set DOMAIN to use HTTPS** in `.env`:
   ```bash
   DOMAIN=https://alima.yourdomain.com
   ```

2. Restart Alima - it will automatically generate HTTPS URLs

That's it! The middleware automatically detects HTTPS from your domain setting.

## License

MIT
