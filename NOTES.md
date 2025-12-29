# Alima 2.0 - Implementation Plan

## Project Overview

**Alima** (AudibleLibraryManager) is a web-based application that downloads audiobooks from Audible accounts and hosts them as RSS feeds for podcast players. It supports multiple Audible accounts, third-party book imports, custom RSS feeds, and master/slave replication for redundancy.

### Key Features
- Web GUI for managing audiobook library
- Multiple Audible account support
- Automatic book downloading and decryption
- Custom RSS feed creation (smart and manual)
- User management with role-based access (admin vs regular users)
- Email invite system
- Third-party audiobook import
- Metadata override system
- Master/slave replication for high availability

---

## Technology Stack

### Backend
- **FastAPI** - Web framework with async support
- **SQLAlchemy 2.0** - ORM for database operations
- **SQLite** - Database (simple, portable, no external services)
- **Jinja2** - Server-side template rendering
- **APScheduler** - Background task scheduling
- **Pydantic** - Data validation and settings management

### Audible Integration
- **audible** (mkb79) - Direct Python API for Audible
- **snowcrypt** - Audio file decryption (.aaxc → .m4a)

### Metadata & Media
- **mutagen** - Read/write audio file metadata
- **Pillow** - Image processing for cover art

### Authentication & Security
- **passlib + bcrypt** - Password hashing
- **python-jose** - JWT tokens for sessions
- **python-multipart** - Form data handling
- **itsdangerous** - Secure token generation for invites
- **starlette-csrf** - CSRF protection for forms

### Email
- **aiosmtplib** - Async SMTP client for sending invites

---

## Database Schema

### Users Table
```sql
- id (PK)
- email (unique, indexed)
- password_hash
- role (enum: 'admin', 'user')
- created_at
- last_login
```

### Invites Table
```sql
- id (PK)
- email
- token (unique, indexed)
- role (default: 'user')
- created_by (FK → Users.id)
- created_at
- expires_at
- used (boolean, default: False)
```

### AudibleAccounts Table
```sql
- id (PK)
- username (unique)
- auth_file_path (path to .json credentials)
- activation_bytes (for decryption)
- marketplace (US, UK, etc.)
- last_sync_timestamp
- enabled (boolean)
- added_at
```

### Books Table
```sql
- id (PK)
- asin (nullable, unique where not null) - Audible books only
- audible_account_id (FK → AudibleAccounts.id, nullable)
- source (enum: 'audible', 'imported')
- file_path (relative path to .m4a/.m4b)
- file_size
- file_format (m4a/m4b)

# Metadata (can be overridden)
- title
- subtitle (nullable)
- author (can be multiple, JSON array or comma-separated)
- narrator (nullable)
- series (nullable)
- series_position (nullable)
- description (text, nullable)
- publisher (nullable)
- publish_date (nullable)
- duration_seconds
- cover_image_path (nullable)
- genres (JSON array, nullable)

# Metadata tracking
- metadata_source (enum: 'audible', 'file', 'manual')
- metadata_override (JSON, nullable) - stores user overrides
- last_metadata_update

# Replication fields
- synced_from_master (boolean, default: False) - for slave instances
- master_book_id (nullable) - reference to book ID on master
- last_replicated_at (nullable)

# Timestamps
- added_at
- downloaded_at (nullable - for queued books)
- last_modified
```

### Feeds Table
```sql
- id (PK)
- user_id (FK → Users.id)
- name
- description (nullable)
- feed_type (enum: 'smart', 'manual')

# For smart feeds
- filter_criteria (JSON, nullable)
  # Examples:
  # {"type": "author", "value": "Brandon Sanderson"}
  # {"type": "series", "value": "Stormlight Archive"}
  # {"type": "narrator", "value": "Michael Kramer"}
  # {"type": "genre", "value": "Fantasy"}
  # {"type": "multiple", "filters": [...]} - for complex criteria

# Feed settings
- is_public (boolean, default: True)
- slug (unique, for URL generation)
- created_at
- updated_at
```

### FeedBooks Table (for manual feeds only)
```sql
- id (PK)
- feed_id (FK → Feeds.id)
- book_id (FK → Books.id)
- position (for manual ordering)
- added_at
```

### DownloadQueue Table
```sql
- id (PK)
- book_id (FK → Books.id)
- audible_account_id (FK → AudibleAccounts.id)
- asin
- priority (integer, higher = sooner)
- status (enum: 'pending', 'downloading', 'decrypting', 'completed', 'failed')
- error_message (nullable)
- attempts (integer, default: 0)
- created_at
- started_at (nullable)
- completed_at (nullable)
```

### ReplicationConfig Table
```sql
- id (PK)
- instance_id (unique UUID, generated on first run)
- instance_name
- mode (enum: 'master', 'slave', 'standalone')
- paired_instance_url (nullable)
- paired_instance_api_key (nullable, encrypted)
- last_sync_from_master (nullable, timestamp)
- created_at
- updated_at
```

### ReplicationLog Table
```sql
- id (PK)
- sync_type (enum: 'book_metadata', 'file_transfer', 'feed_sync', 'full')
- direction (enum: 'push', 'pull')
- status (enum: 'pending', 'in_progress', 'completed', 'failed')
- items_synced (integer)
- bytes_transferred (nullable)
- error_message (nullable)
- started_at
- completed_at
```

---

## Application Structure

```
alima/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI application entry point
│   ├── config.py               # Configuration (env vars, settings)
│   ├── database.py             # SQLAlchemy setup, session management
│   ├── models.py               # SQLAlchemy ORM models
│   ├── schemas.py              # Pydantic schemas for validation
│   ├── auth.py                 # Authentication utilities
│   ├── dependencies.py         # FastAPI dependency injection
│   │
│   ├── routers/                # Route handlers
│   │   ├── __init__.py
│   │   ├── auth.py             # Login, logout, accept invite, profile
│   │   ├── library.py          # Browse books, search, filter
│   │   ├── books.py            # Book detail, edit metadata
│   │   ├── feeds.py            # Feed CRUD, preview
│   │   ├── accounts.py         # Audible account management (admin)
│   │   ├── admin.py            # User invites, system status (admin)
│   │   ├── rss.py              # RSS feed generation (public)
│   │   ├── files.py            # Static file serving (audiobooks, covers)
│   │   ├── replication_api.py  # API endpoints for master/slave communication
│   │   └── replication_admin.py # Admin UI for pairing, monitoring
│   │
│   ├── services/               # Business logic
│   │   ├── __init__.py
│   │   ├── audible_sync.py     # Fetch library from Audible API
│   │   ├── book_download.py    # Download & decrypt books
│   │   ├── book_import.py      # Import third-party books
│   │   ├── metadata.py         # Read/write audio metadata
│   │   ├── feed_generator.py   # Generate RSS XML
│   │   ├── email_service.py    # Send invite emails
│   │   ├── search.py           # Book search/filter logic
│   │   └── replication/
│   │       ├── __init__.py
│   │       ├── master_service.py    # Push to slaves
│   │       ├── slave_service.py     # Pull from master
│   │       └── sync_strategy.py     # rsync vs HTTP strategy
│   │
│   ├── workers/                # Background tasks
│   │   ├── __init__.py
│   │   ├── scheduler.py        # APScheduler setup
│   │   ├── sync_worker.py      # Periodic sync job
│   │   └── replication_worker.py # Periodic replication job
│   │
│   ├── middleware/
│   │   └── readonly.py         # Enforce read-only on slaves
│   │
│   ├── templates/              # Jinja2 templates
│   │   ├── base.html
│   │   ├── components/         # Reusable template parts
│   │   ├── auth/
│   │   │   ├── login.html
│   │   │   └── accept_invite.html
│   │   ├── library/
│   │   │   ├── index.html      # Library grid/list view
│   │   │   └── book_detail.html
│   │   ├── feeds/
│   │   │   ├── index.html      # User's feeds list
│   │   │   ├── create.html
│   │   │   └── edit.html
│   │   └── admin/
│   │       ├── accounts.html   # Audible accounts
│   │       ├── invites.html
│   │       ├── system.html     # Status, queue, logs
│   │       └── replication.html # Master/slave pairing, monitoring
│   │
│   └── static/                 # Static assets
│       ├── css/
│       │   └── main.css
│       ├── js/
│       │   └── main.js         # Minimal JS for forms, etc.
│       └── images/
│
├── data/                       # Persistent data (Docker volume)
│   ├── db/
│   │   └── alima.db           # SQLite database
│   ├── audiobooks/            # .m4a/.m4b files
│   ├── covers/                # Cover images
│   ├── audible_auth/          # Audible .json credential files
│   └── temp/                  # Temporary download directory
│
├── tests/
│   ├── __init__.py
│   ├── test_auth.py
│   ├── test_library.py
│   ├── test_feeds.py
│   └── test_services.py
│
├── alembic/                   # Database migrations (optional but recommended)
│   ├── versions/
│   └── env.py
│
├── cli.py                     # CLI commands (create admin, reset password, etc.)
├── Dockerfile
├── docker-compose.yml         # Optional, for easier development
├── requirements.txt
├── .env.example              # Example environment variables
├── README.md
└── NOTES.md                  # This file
```

---

## Core Features & Implementation Order

Build in this order to get a working system quickly, then iterate:

### Phase 1: Foundation (Get something running)
1. **Project setup**: Create directory structure, virtual environment, requirements.txt
2. **Database models**: Define all SQLAlchemy models
3. **Basic FastAPI app**: Main app, health check endpoint
4. **Authentication**: Login/logout with session management
5. **Admin CLI**: Create first admin user via command line

### Phase 2: Audible Integration (Core functionality)
6. **Audible account management**: Admin can add Audible accounts
7. **Library sync service**: Fetch book list from Audible API, populate database
8. **Book download worker**: Queue and download books from Audible
9. **Decryption**: Integrate snowcrypt to decrypt .aaxc → .m4a
10. **Basic library view**: Display all books in a simple grid/list

### Phase 3: User Management
11. **Invite system**: Admin can send email invites
12. **User registration**: Accept invite, create account
13. **Role-based access**: Middleware to enforce admin vs user permissions

### Phase 4: Book Management
14. **Book detail page**: View full metadata
15. **Metadata reading**: Extract metadata from audio files
16. **Metadata override**: Edit title, author, series, etc.
17. **Cover image handling**: Store and serve cover art

### Phase 5: Third-Party Books
18. **Import service**: Admin uploads .m4a/.m4b files
19. **Metadata extraction**: Read embedded metadata
20. **Manual metadata entry**: Form to add/edit metadata

### Phase 6: RSS Feeds
21. **Feed CRUD**: Create, edit, delete feeds
22. **Smart feed filters**: Author, series, narrator, genre
23. **Manual feed management**: Add/remove books to custom feeds
24. **RSS generator**: Generate valid podcast RSS XML
25. **Feed preview**: Show what books are in a feed before subscribing

### Phase 7: Polish & Production
26. **Background sync worker**: Automatic periodic syncing (every hour/day)
27. **Replication system**:
    - 27a. Replication configuration and pairing
    - 27b. Master → Slave metadata sync via API
    - 27c. Master → Slave file sync via rsync
    - 27d. Read-only enforcement on slaves
    - 27e. Replication monitoring UI
28. **Download queue UI**: Show what's downloading, retry failed
29. **Search & filters**: Search library by title, author, series
30. **Frontend styling**: Make it look nice (CSS framework like Tailwind or Bootstrap)
31. **Error handling**: Proper error pages, logging
32. **Docker optimization**: Multi-stage build, smaller image
33. **Documentation**: README, setup guide

---

## Key Implementation Details

### Authentication Flow

**Login:**
1. User submits email + password
2. Check database for user
3. Verify password hash with bcrypt
4. Create JWT session token
5. Set HTTP-only cookie
6. Redirect to library

**Invite:**
1. Admin enters email + role on admin page
2. Generate secure random token (itsdangerous)
3. Store invite in database with expiration (e.g., 7 days)
4. Send email with link: `https://alima.example.com/auth/accept-invite?token=...`
5. User clicks link, sees registration form (pre-filled email)
6. User sets password, submits
7. Mark invite as used, create user account

**CLI Reset:**
```bash
python cli.py reset-password --email user@example.com --password newpass
```

### Audible Sync Process

**Initial Sync:**
1. Admin adds Audible account (username, uploads auth .json file, provides activation bytes)
2. System stores account in database
3. Background worker (or manual trigger) starts sync:
   - Load auth from file: `auth = Authenticator.from_file(path)`
   - Create client: `client = Client(auth)`
   - Fetch library: `client.get("library", params={...})`
   - For each book in response:
     - Check if ASIN exists in database
     - If new: Create Book record with metadata
     - If exists: Update metadata if changed
     - If not downloaded: Add to DownloadQueue
   - Update `last_sync_timestamp` on account

**Download Worker:**
1. Runs periodically (every 5-10 minutes)
2. Query `DownloadQueue` for pending items, ordered by priority
3. For each item:
   - Update status to 'downloading'
   - Get download link: `client.post(f"content/{asin}/licenserequest", ...)`
   - Download .aaxc file to temp directory
   - Get voucher: `decrypt_voucher_from_licenserequest(auth, license_response)`
   - Save voucher as .json
   - Update status to 'decrypting'
   - Decrypt with snowcrypt: `snowcrypt.decrypt_aaxc(...)`
   - Move .m4a to final location
   - Extract metadata, save cover image
   - Update Book record with file_path, downloaded_at
   - Update status to 'completed'
   - On error: Increment attempts, set status to 'failed', store error_message

### Third-Party Book Import

**Upload Flow (Admin only):**
1. Admin goes to "Import Book" page
2. Uploads .m4a/.m4b file
3. System reads embedded metadata using mutagen:
   - Title, artist (author), album (series?), comment (description)
   - Cover art (extract from file)
   - Duration
4. Pre-fill form with extracted metadata
5. Admin reviews/edits metadata
6. Submit: Creates Book record with source='imported'
7. Move file to permanent location

### Feed System

**Smart Feeds:**
- Dynamically generated based on filter criteria
- Examples:
  ```json
  // Author feed
  {"type": "author", "value": "Brandon Sanderson"}

  // Series feed
  {"type": "series", "value": "The Stormlight Archive"}

  // Multi-condition feed
  {
    "type": "and",
    "conditions": [
      {"type": "genre", "value": "Fantasy"},
      {"type": "narrator", "value": "Michael Kramer"}
    ]
  }
  ```
- When RSS is requested: Query Books table with filters, generate XML

**Manual Feeds:**
- User explicitly adds books to feed
- Stored in FeedBooks junction table
- Can manually reorder (position field)
- When RSS is requested: Query FeedBooks → Books, generate XML

**RSS Generation:**
- Endpoint: `GET /feeds/{slug}.xml`
- No authentication required
- Query feed by slug
- If smart: Apply filters to get books
- If manual: Join FeedBooks → Books
- Generate RSS XML:
  ```xml
  <?xml version="1.0" encoding="UTF-8"?>
  <rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
    <channel>
      <title>{feed.name}</title>
      <description>{feed.description}</description>
      <language>en-us</language>
      <itunes:author>Alima</itunes:author>

      <item>
        <title>{book.title}</title>
        <itunes:author>{book.author}</itunes:author>
        <description>{book.description}</description>
        <enclosure url="https://domain.com/audiobooks/{book.file_path}"
                   length="{book.file_size}" type="audio/x-m4a"/>
        <guid>{book.id}</guid>
        <pubDate>{book.added_at in RFC822}</pubDate>
        <itunes:duration>{book.duration_seconds}</itunes:duration>
        <itunes:image href="https://domain.com/covers/{book.cover_image_path}"/>
      </item>
      ...
    </channel>
  </rss>
  ```

### Static File Serving

**Audiobook Files:**
```python
# routers/files.py
@router.get("/audiobooks/{file_path:path}")
async def serve_audiobook(file_path: str):
    """Stream audiobook files with range request support for podcast players"""
    full_path = Path(config.AUDIOBOOKS_PATH) / file_path

    # Security: Prevent path traversal
    if not full_path.resolve().is_relative_to(Path(config.AUDIOBOOKS_PATH).resolve()):
        raise HTTPException(404, "File not found")

    if not full_path.exists():
        raise HTTPException(404, "File not found")

    # Return FileResponse with media type and range support
    return FileResponse(
        full_path,
        media_type="audio/x-m4a",
        headers={"Accept-Ranges": "bytes"}
    )
```

**Cover Images:**
```python
@router.get("/covers/{file_path:path}")
async def serve_cover(file_path: str):
    """Serve cover images"""
    full_path = Path(config.COVERS_PATH) / file_path

    # Security: Prevent path traversal
    if not full_path.resolve().is_relative_to(Path(config.COVERS_PATH).resolve()):
        raise HTTPException(404, "Image not found")

    if not full_path.exists():
        raise HTTPException(404, "Image not found")

    # Detect image type and return
    media_type = "image/jpeg"  # or detect from extension
    return FileResponse(full_path, media_type=media_type)
```

### Metadata Override System

**Storage:**
- `Book.metadata_override` is a JSON field
- Stores user-provided overrides: `{"title": "My Custom Title", "author": "Custom Author"}`

**Display Logic:**
```python
def get_display_metadata(book):
    # Start with base metadata
    metadata = {
        "title": book.title,
        "author": book.author,
        "narrator": book.narrator,
        # ... etc
    }

    # Apply overrides if present
    if book.metadata_override:
        metadata.update(book.metadata_override)

    return metadata
```

**Edit Form:**
- Show current effective metadata (with overrides applied)
- User edits any field
- On save: Store only changed fields in `metadata_override`
- Can "reset to original" by clearing override for specific field

---

## Master/Slave Replication

### Overview

The system supports master/slave replication for high availability. The master instance handles all downloads and syncs, while slave instances receive read-only copies of the library.

**Modes:**
- **Standalone**: Single instance, no replication
- **Master**: Downloads books, syncs library, pushes to slaves
- **Slave**: Receives books from master, read-only for book management

### Configuration

**Environment Variables (.env):**
```bash
# Replication Mode
REPLICATION_MODE=master  # or 'slave' or 'standalone'

# Master Configuration (for slave instances)
MASTER_URL=https://master.alima.example.com
MASTER_API_KEY=<secure-generated-key>

# Slave Configuration (for master instances)
SLAVE_INSTANCES=https://slave1.alima.example.com,https://slave2.alima.example.com

# Sync Settings
REPLICATION_SYNC_INTERVAL_MINUTES=15  # How often slave pulls from master
REPLICATION_METHOD=http  # Default: 'http' (or 'rsync' for SSH-based sync)

# Optional: rsync configuration (only needed if REPLICATION_METHOD=rsync)
# RSYNC_USER=snow
# RSYNC_HOST=richmond
# RSYNC_PATH=/var/www/snowden/
```

### Pairing Process

**Master initiates pairing:**
1. Admin goes to "Replication" admin page
2. Clicks "Add Slave Instance"
3. Enters slave URL: `https://slave.alima.example.com`
4. Master generates API key, displays pairing command:
   ```bash
   # Run this on the slave instance:
   python cli.py pair-with-master \
     --master-url https://master.alima.example.com \
     --api-key <generated-key>
   ```
5. Admin runs command on slave
6. Slave stores master URL + API key, sets mode to 'slave'
7. Slave makes test request to master to verify pairing
8. Master receives verification, adds slave to `SLAVE_INSTANCES` config
9. Initial full sync begins

### Replication Strategies

**HTTP API-based (recommended)**
- Slave polls master API for new books
- Downloads files via HTTP endpoints with streaming support
- Metadata synced via HTTP API
- Pros: No SSH needed, firewall-friendly, simpler to maintain
- Cons: Slightly slower than rsync, but adequate for typical usage

**Optional: rsync fallback**
- Can be enabled for very large libraries or limited bandwidth scenarios
- Requires SSH access between instances
- Configured via `REPLICATION_METHOD=rsync` env var

### Master Sync Process

```python
# Runs periodically on master
async def sync_to_slaves():
    slaves = get_configured_slaves()

    for slave_url in slaves:
        # 1. Get slave's last sync timestamp
        last_sync = await get_slave_last_sync(slave_url)

        # 2. Get books added/modified since last sync
        changed_books = get_books_changed_since(last_sync)

        # 3. Push metadata to slave via API
        await push_metadata_to_slave(slave_url, changed_books)

        # 4. Sync files via HTTP (default) or rsync if configured
        if config.REPLICATION_METHOD == 'rsync':
            await rsync_audiobooks_to_slave(slave_url)
        else:
            # HTTP is the default - files will be pulled by slave
            pass

        # 5. Update replication log
        log_sync_completion(slave_url, len(changed_books))
```

### Slave Sync Process

```python
# Runs periodically on slave
async def sync_from_master():
    master_url = config.MASTER_URL

    # 1. Get our last sync timestamp
    last_sync = get_last_sync_from_master()

    # 2. Request changed books from master
    response = await http_client.get(
        f"{master_url}/api/replication/changed-books",
        params={"since": last_sync},
        headers={"X-API-Key": config.MASTER_API_KEY}
    )
    changed_books = response.json()

    # 3. Update local database with new metadata
    for book_data in changed_books:
        upsert_book_from_master(book_data)

    # 4. Download missing/updated files via HTTP
    for book_data in changed_books:
        if not local_file_exists_and_matches(book_data):
            await download_file_from_master(book_data['id'])

    # Optional: If rsync is configured, wait for master to push instead
    if config.REPLICATION_METHOD == 'rsync':
        # Master pushes via rsync, skip HTTP download
        pass

    # 5. Update last sync timestamp
    update_last_sync_timestamp()
```

### API Endpoints

**Master Endpoints:**
```python
# Authenticated with API key
@router.get("/api/replication/changed-books")
async def get_changed_books(
    since: datetime,
    api_key: str = Header(..., alias="X-API-Key")
):
    # Verify API key belongs to known slave
    # Return books changed since timestamp

@router.post("/api/replication/verify-pairing")
async def verify_pairing(api_key: str = Header(...)):
    # Slave calls this to test connection

@router.get("/api/replication/audiobooks/{book_id}")
async def download_audiobook_file(book_id: int, api_key: str = Header(...)):
    """Stream audiobook file for HTTP-based sync"""
    # Verify API key belongs to known slave
    # Get book from database
    # Return FileResponse with .m4a/.m4b file, range support enabled
    return FileResponse(
        book.file_path,
        media_type="audio/x-m4a",
        headers={"Accept-Ranges": "bytes"}
    )

@router.get("/api/replication/covers/{book_id}")
async def download_cover_file(book_id: int, api_key: str = Header(...)):
    """Stream cover image for HTTP-based sync"""
    # Verify API key belongs to known slave
    # Get book from database
    # Return FileResponse with cover image
```

**Slave Endpoints:**
```python
@router.post("/api/replication/receive-metadata")
async def receive_metadata_from_master(
    books: List[BookSchema],
    api_key: str = Header(...)
):
    # Master pushes metadata updates
    # Upsert books in local database

@router.get("/api/replication/last-sync")
async def get_last_sync_timestamp(api_key: str = Header(...)):
    # Master queries when slave was last synced
```

### Read-Only Enforcement on Slaves

```python
# middleware/readonly.py
async def enforce_readonly(request: Request, call_next):
    if config.REPLICATION_MODE == 'slave':
        # Block these operations:
        blocked_paths = [
            '/admin/accounts/add',      # Can't add Audible accounts
            '/admin/import',             # Can't import books
            '/admin/accounts/sync',      # Can't trigger syncs
            '/books/*/delete',           # Can't delete books
        ]

        if any(request.url.path.startswith(path) for path in blocked_paths):
            raise HTTPException(403, "Read-only slave instance")

    return await call_next(request)
```

### Optional: Rsync Implementation

**Note**: HTTP-based replication is the default. This rsync approach is optional for advanced users with very large libraries.

```python
async def rsync_audiobooks_to_slave(slave_config):
    """Push audiobooks and covers to slave via rsync (optional, for large libraries)"""

    # Parse slave rsync configuration
    rsync_user = slave_config.get('rsync_user', 'snow')
    rsync_host = slave_config.get('rsync_host')
    rsync_path = slave_config.get('rsync_path')

    # Rsync audiobooks
    await run_rsync(
        source="/app/data/audiobooks/",
        destination=f"{rsync_user}@{rsync_host}:{rsync_path}/audiobooks/",
        options="--verbose -raz --exclude '*.xml' --exclude 'cover.jpg'"
    )

    # Rsync covers
    await run_rsync(
        source="/app/data/covers/",
        destination=f"{rsync_user}@{rsync_host}:{rsync_path}/covers/",
        options="--verbose -raz"
    )
```

**To enable rsync replication:**
1. Set `REPLICATION_METHOD=rsync` in .env
2. Install rsync and openssh-client in Docker image
3. Mount SSH keys into container
4. Configure rsync settings (RSYNC_USER, RSYNC_HOST, RSYNC_PATH)

### Feed Behavior on Slaves

**Important**: Feeds work identically on slaves
- Slaves have full metadata database (synced from master)
- RSS feed generation works normally
- Users can create custom feeds on slaves
- Feed configurations are NOT synced (slave feeds are independent)
- Only book metadata + files are synced

### Admin UI - Replication Page

- **Standalone mode**: Option to "Become Master" or "Pair as Slave"
- **Master mode**:
  - List paired slaves with status (last sync, items synced)
  - "Add Slave" button → generates pairing command
  - Manual "Push Now" button
  - Sync logs table
- **Slave mode**:
  - Show master URL, connection status
  - Last sync timestamp
  - Manual "Pull Now" button
  - "Unpair" button
  - Note: "This instance is read-only for book management"

---

## Configuration

### Environment Variables (.env)

```bash
# App
APP_NAME=Alima
SECRET_KEY=<generate-random-secret>
DOMAIN=https://alima.example.com

# Database
DATABASE_URL=sqlite:///data/db/alima.db

# Paths
AUDIOBOOKS_PATH=/app/data/audiobooks
COVERS_PATH=/app/data/covers
AUDIBLE_AUTH_PATH=/app/data/audible_auth
TEMP_PATH=/app/data/temp

# Email (optional, for invites)
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=alima@example.com
SMTP_PASSWORD=<smtp-password>
SMTP_FROM=alima@example.com

# Sync Settings
SYNC_INTERVAL_HOURS=6
DOWNLOAD_QUALITY=Extreme  # Extreme, High, Normal

# Session
SESSION_EXPIRE_HOURS=168  # 7 days
INVITE_EXPIRE_DAYS=7

# Replication Mode
REPLICATION_MODE=master  # or 'slave' or 'standalone'

# Master Configuration (for slave instances)
MASTER_URL=https://master.alima.example.com
MASTER_API_KEY=<secure-generated-key>

# Slave Configuration (for master instances)
SLAVE_INSTANCES=https://slave1.alima.example.com,https://slave2.alima.example.com

# Sync Settings
REPLICATION_SYNC_INTERVAL_MINUTES=15
REPLICATION_METHOD=http  # Default: 'http' (or 'rsync' for SSH-based sync)

# Optional: rsync configuration (only needed if REPLICATION_METHOD=rsync)
# RSYNC_USER=snow
# RSYNC_HOST=richmond
# RSYNC_PATH=/var/www/snowden/
```

---

## CLI Commands

```bash
# Create initial admin user
python cli.py create-admin --email admin@example.com --password <password>

# Reset password
python cli.py reset-password --email user@example.com

# Trigger manual sync
python cli.py sync --all
python cli.py sync --account snowskeleton

# Import existing Audible account from old system
python cli.py import-account \
  --username snowskeleton \
  --auth-file /path/to/.audible/snowskeleton.json \
  --activation-bytes b2760503

# Scan and import existing audiobooks from old system
python cli.py scan-audiobooks --path /path/to/audiobooks/

# Import existing books from old system (legacy command)
python cli.py import-legacy --path /path/to/old/audiobooks

# Database migrations
python cli.py migrate-db

# Replication commands
python cli.py set-mode --mode master

# Pair as slave (run on slave instance)
python cli.py pair-with-master \
  --master-url https://master.alima.example.com \
  --api-key <key>

# Generate pairing key for slave (run on master)
python cli.py generate-slave-key --slave-url https://slave.alima.example.com

# Manual sync
python cli.py replicate-now --direction push  # master → slaves
python cli.py replicate-now --direction pull  # slave ← master

# Unpair
python cli.py unpair  # slave disconnects from master
python cli.py remove-slave --url https://slave.alima.example.com  # master removes slave

# Migration: Import from old sync setup
python cli.py import-from-richmond \
  --rsync-user snow \
  --rsync-host richmond \
  --rsync-path /var/www/snowden/
```

---

## First Run / Bootstrap Process

When setting up Alima 2.0 for the first time:

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Copy .env.example to .env and configure
cp .env.example .env
# Edit .env with your settings (SECRET_KEY, DOMAIN, SMTP, etc.)

# 3. Initialize database
python cli.py migrate-db

# 4. Create first admin user
python cli.py create-admin --email admin@example.com --password secure_password

# 5. Run the application
uvicorn app.main:app --reload

# 6. Access the application
# Open http://localhost:8000 in your browser
# Login with admin credentials
# Go to Admin > Audible Accounts to add your first account
```

---

## Docker Setup

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Optional: Add rsync and openssh-client if using rsync replication
# RUN apt-get update && apt-get install -y rsync openssh-client && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app/ ./app/
COPY cli.py .

# Create data directories
RUN mkdir -p /app/data/db \
             /app/data/audiobooks \
             /app/data/covers \
             /app/data/audible_auth \
             /app/data/temp

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### docker-compose.yml (for development)

```yaml
version: '3.8'

services:
  alima:
    build: .
    container_name: alima
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
      - ./app:/app/app  # Development: live reload
      # Optional: Only needed if using rsync replication (REPLICATION_METHOD=rsync)
      # - ~/.ssh:/root/.ssh:ro  # For rsync (ensure private key has chmod 600 permissions)
    env_file:
      - .env
    environment:
      - ENVIRONMENT=development
```

### Production Volume Mount

```bash
docker run -d \
  --name alima \
  -p 8000:8000 \
  -v /path/to/data:/app/data \
  --env-file .env \
  alima:latest

# Optional: Add SSH volume if using rsync replication
# -v /home/user/.ssh:/root/.ssh:ro \
```

---

## Dependencies (requirements.txt)

```txt
# Web Framework
fastapi==0.109.0
uvicorn[standard]==0.27.0
jinja2==3.1.3
python-multipart==0.0.6

# Database
sqlalchemy==2.0.25
alembic==1.13.1

# Auth & Security
passlib[bcrypt]==1.7.4
python-jose[cryptography]==3.3.0
itsdangerous==2.1.2
starlette-csrf==2.1.0

# Audible
audible==0.9.1
snowcrypt==0.1.3.post0

# Metadata & Media
mutagen==1.47.0
Pillow==10.2.0

# Email
aiosmtplib==3.0.1

# Background Tasks
apscheduler==3.10.4

# HTTP Client (for downloads)
httpx==0.26.0

# Utilities
python-dotenv==1.0.1
```

---

## Security Considerations

1. **Password Storage**: bcrypt with cost factor 12
2. **Session Tokens**: JWT with HTTP-only cookies, no localStorage
3. **Invite Tokens**: Cryptographically secure random tokens (itsdangerous)
4. **File Uploads**: Validate file types, scan for suspicious content
5. **Path Traversal**: Sanitize all file paths, use absolute paths
6. **SQL Injection**: Protected by SQLAlchemy ORM
7. **XSS**: Jinja2 auto-escapes by default
8. **CSRF**: Use FastAPI CSRF middleware for forms
9. **Rate Limiting**: Add slowapi for login attempts
10. **HTTPS**: Enforce in production (reverse proxy like nginx/Traefik)
11. **Replication Security**:
    - API keys stored encrypted in database
    - SSH keys for rsync with limited permissions
    - TLS required for master/slave communication
    - Validate all incoming metadata before insertion

---

## Migration from Old System (alima-docker)

### Current System Architecture

**Components:**
1. **alima-docker** - Main orchestration container
2. **rsrssb** - RSS feed generator for audiobooks
3. **snowcrypt** - Pure Python decryption tool for .aaxc/.aax files
4. **audible-cli** - CLI wrapper around the Audible package (used via shell commands)
5. **Audible** (mkb79) - The underlying Python API library

**Current Data Flow:**
```
main.py (runs every 60 seconds)
  ├─> For each user account:
  │   ├─> Download new books since last timestamp (audible-cli)
  │   │   └─> Downloads .aaxc + .voucher files
  │   ├─> Decrypt files using snowcrypt (bytes parameter)
  │   │   └─> Converts .aaxc → .m4a
  │   └─> Move .m4a files to /app/data/audiobooks/
  │
  ├─> generate.sh - Creates RSS feed using rsrssb
  │   └─> Outputs feed.xml with all audiobooks
  │
  └─> sync.sh - Syncs to remote server via rsync
      └─> Bidirectional sync with snow@richmond
```

**Current User Accounts:**
- snowskeleton (bytes: b2760503)
- lyonsden (bytes: 173e1e01)
- noslen (bytes: 85d43808)
- brianfroeb (bytes: e1c7262f)
- feartheartist (bytes: 8de2ce05)

### Migration Strategy

1. **Export existing data**:
   - Existing .m4a files in `/app/data/audiobooks/`
   - Existing Audible auth files from `.audible/*.json`
   - Timestamp files for reference

2. **Import process**:
   ```bash
   # Import Audible accounts
   python cli.py import-account \
     --username snowskeleton \
     --auth-file /old/path/.audible/snowskeleton.json \
     --activation-bytes b2760503

   python cli.py import-account \
     --username lyonsden \
     --auth-file /old/path/.audible/lyonsden.json \
     --activation-bytes 173e1e01

   python cli.py import-account \
     --username noslen \
     --auth-file /old/path/.audible/noslen.json \
     --activation-bytes 85d43808

   python cli.py import-account \
     --username brianfroeb \
     --auth-file /old/path/.audible/brianfroeb.json \
     --activation-bytes e1c7262f

   python cli.py import-account \
     --username feartheartist \
     --auth-file /old/path/.audible/feartheartist.json \
     --activation-bytes 8de2ce05

   # Scan and import existing audiobooks
   python cli.py scan-audiobooks --path /old/path/audiobooks/
   ```

3. **Setup replication**:
   - Deploy new Alima 2.0 as master on your main server
   - Deploy Alima 2.0 as slave on `richmond`
   - Run pairing command
   - Initial sync will copy all books to slave
   - Ongoing syncs happen automatically every 15 minutes (configurable)

4. **Verification**:
   - Manually check a few books in web UI
   - Trigger sync to catch any missing books
   - Generate RSS feed and test with podcast app

---

## Testing Strategy

**Unit Tests:**
- Models: CRUD operations
- Services: Business logic (sync, download, metadata)
- Auth: Login, invite, permissions
- Replication: Master/slave sync logic

**Integration Tests:**
- API endpoints: Full request/response cycle
- Background workers: Sync, download queue, replication
- RSS generation: Valid XML output

**Manual Testing:**
- Full user flow: Invite → register → browse → create feed
- Admin flow: Add account → sync → download → import
- RSS feed: Subscribe in podcast app, verify playback
- Replication: Pair master/slave, verify sync

---

## Future Enhancements (Not in Phase 1)

- **Statistics**: Listen tracking, most popular books
- **Collections/Tags**: Organize books beyond feeds
- **Download History**: Track what's been synced
- **Webhook Notifications**: Alert on new books
- **Multi-user RSS**: Private feeds with tokens
- **Book Sharing**: Share specific books with other users
- **Advanced Search**: Full-text search, fuzzy matching
- **Batch Operations**: Bulk metadata edit
- **Audit Log**: Track all admin actions
- **API**: REST API for third-party integration
- **Mobile App**: Companion app for easier browsing
- **Postgres support**: For larger deployments
- **Multi-master replication**: For complex topologies

---

## Notes

- All books from all Audible accounts should always be downloaded automatically
- Regular users cannot delete books, upload books, or manage Audible accounts
- Admin users can send email invites, manage accounts, import books
- RSS feeds require no authentication to access
- Feeds on slave instances are independent (not synced from master)
- Metadata can be overridden on a per-book basis for all books
- Third-party books are typically m4a or m4b format
- System should work in any environment (with or without Docker)
