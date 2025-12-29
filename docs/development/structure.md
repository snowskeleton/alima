# Project Structure

Understanding how Alima is organized.

## Directory Layout

```
alima2.0/
├── app/                    # Main application code
│   ├── main.py            # FastAPI entry point
│   ├── config.py          # Configuration management
│   ├── database.py        # Database setup
│   ├── models.py          # SQLAlchemy models
│   ├── dependencies.py    # FastAPI dependencies
│   │
│   ├── routers/           # API route handlers
│   │   ├── auth.py        # Authentication
│   │   ├── admin.py       # Admin operations
│   │   ├── accounts.py    # Audible accounts
│   │   ├── library.py     # Library browsing
│   │   ├── books.py       # Book operations
│   │   ├── feeds.py       # Feed management
│   │   ├── rss.py         # RSS generation
│   │   ├── import_books.py
│   │   ├── settings.py
│   │   └── files.py
│   │
│   ├── services/          # Business logic
│   │   ├── audible_service.py
│   │   ├── email_service.py
│   │   ├── settings_service.py
│   │   └── snowcrypt_service.py
│   │
│   ├── workers/           # Background tasks
│   │   └── scheduler.py
│   │
│   ├── templates/         # Jinja2 templates
│   │   ├── base.html
│   │   ├── auth/
│   │   ├── admin/
│   │   └── library/
│   │
│   └── static/            # CSS, JS, images
│       ├── css/
│       ├── js/
│       └── images/
│
├── tests/                 # Test suite
│   ├── conftest.py        # Pytest fixtures
│   ├── test_auth.py
│   ├── test_admin.py
│   └── ...
│
├── data/                  # Runtime data (gitignored)
│   ├── db/               # SQLite database
│   ├── audiobooks/       # Downloaded books
│   ├── covers/           # Cover images
│   ├── audible_auth/     # Auth files
│   └── temp/             # Temporary files
│
├── docs/                  # Documentation
├── .env                   # Environment config (gitignored)
├── .env.example          # Example environment
├── requirements.txt      # Python dependencies
├── mkdocs.yml           # Documentation config
└── README.md            # Project readme
```

## Application Layers

### 1. Entry Point (`main.py`)

- Creates FastAPI application
- Registers routers
- Handles application lifecycle
- Mounts static files

### 2. Configuration (`config.py`)

- Uses Pydantic Settings
- Loads from `.env` file
- Type-safe configuration
- Environment variable support

### 3. Database Layer (`database.py`, `models.py`)

- SQLAlchemy 2.0 ORM
- SQLite by default (PostgreSQL supported)
- Typed mappings with `Mapped[T]`
- Session management

### 4. Routers

FastAPI routers organized by feature:

- **auth** - Login, registration, session management
- **admin** - User and invite management
- **accounts** - Audible account operations
- **library** - Audiobook browsing
- **books** - Individual book operations
- **feeds** - RSS feed CRUD
- **rss** - RSS XML generation
- **settings** - Server configuration
- **files** - Static file serving

### 5. Services

Business logic separated from routes:

- **AudibleService** - Audible API integration
- **EmailService** - SMTP email sending
- **SettingsService** - Encrypted settings management
- **SnowcryptService** - Credential encryption

### 6. Workers

Background tasks using APScheduler:

- Automatic library syncing
- Download management
- Cleanup tasks

### 7. Templates

Server-side rendered HTML using Jinja2:

- Extends `base.html`
- Component-based structure
- Inline CSS and JavaScript

## Key Patterns

### Dependency Injection

FastAPI dependencies for:

- Database sessions: `db: Session = Depends(get_db)`
- Authentication: `current_user: User = Depends(get_current_user)`
- Admin check: `current_user: User = Depends(require_admin)`

### Async Operations

All I/O operations use async/await:

- HTTP requests
- Email sending
- File operations
- Database queries (with sync wrapper)

### Type Safety

- Type hints throughout
- Pydantic models for validation
- SQLAlchemy typed mappings
- MyPy compatible

### Configuration Hierarchy

1. Environment variables (`.env`)
2. Database settings (via web UI)
3. Defaults in code

Database settings override environment variables.

## Data Flow

### Authentication Flow

```
User → Router → Dependencies → Database
  ↓
Session Cookie ← Response
```

### Library Sync Flow

```
Scheduler → AudibleService → Audible API
                  ↓
              Database ← Metadata
                  ↓
           File System ← Covers
```

### RSS Feed Flow

```
Podcast App → RSS Router → Database
                 ↓
            RSS XML ← Template
```

## Testing Structure

Tests mirror the application structure:

- `conftest.py` - Fixtures and test database setup
- `test_*.py` - One file per router/service
- Async test support with pytest-asyncio
- FastAPI TestClient for route testing

## Adding New Features

To add a new feature:

1. **Create models** in `models.py` if needed
2. **Create service** in `services/` for business logic
3. **Create router** in `routers/` for API endpoints
4. **Create templates** in `templates/` for UI
5. **Register router** in `main.py`
6. **Write tests** in `tests/`
7. **Update docs** in `docs/`

## Best Practices

### Route Handlers

- Keep thin - delegate to services
- Use dependencies for common logic
- Return appropriate response types
- Add docstrings for API docs

### Services

- Pure business logic
- No HTTP/request handling
- Testable in isolation
- Use type hints

### Templates

- Extend base.html
- Use components for reusability
- Keep JavaScript minimal
- Inline styles for simplicity

### Database

- Use transactions
- Close sessions properly
- Use indexes for queries
- Avoid N+1 queries
